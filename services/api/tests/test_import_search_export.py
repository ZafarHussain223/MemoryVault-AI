import base64
import io
import json
import socket
import zipfile
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_workflows import client, database, register, note
from app.db import DB, Document, now
from app import imports


def test_public_import_sanitizes_extracts_and_records_source(client, monkeypatch):
    register(client)
    monkeypatch.setattr(imports, 'fetch_public', lambda *args: ('https://example.com/article', 'text/html', b'<title>Solar research</title><nav>Menu</nav><article><h1>Solar research</h1><p>Solar panels convert sunlight into electrical energy.</p><script>secret_bad_script()</script></article>'))
    response = client.post('/api/v1/imports', json={'url': 'https://example.com/article', 'kind': 'webpage'})
    assert response.status_code == 201, response.text
    doc = client.get('/api/v1/documents/'+response.json()['id']).json()
    assert doc['status'] == 'ready'
    assert doc['source_url'] == 'https://example.com/article'
    assert doc['source_type'] == 'webpage'
    assert 'secret_bad_script' not in doc['content'] and 'Menu' not in doc['content']
    assert client.get('/api/v1/search', params={'q': 'sunlight', 'kind': 'link'}).json()['items'][0]['document_id'] == doc['id']
    assert client.post('/api/v1/imports', json={'url':'https://example.com/article'}).status_code == 409


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'https://user:password@example.com/', 'http://localhost/', 'http://127.0.0.1/', 'http://[::1]/', 'http://169.254.169.254/', 'https://example.com:8443/'])
def test_import_blocks_private_and_invalid_destinations(url, monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (host if host[0].isdigit() else '127.0.0.1', 80))])
    with pytest.raises(HTTPException) as exc:
        imports.public_target(url)
    assert exc.value.status_code == 422


def test_mixed_dns_answers_blocked_and_redirect_revalidated(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('93.184.216.34',443)), (2,1,6,'',('10.0.0.1',443))])
    with pytest.raises(HTTPException): imports.public_target('https://example.com/')
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('93.184.216.34',443))])
    response = Mock(status=302)
    response.getheader.return_value = 'http://localhost/admin'
    connection = Mock()
    connection.getresponse.return_value = response
    make = Mock(return_value=connection)
    monkeypatch.setattr(imports, 'PinnedHTTPS', make)
    with pytest.raises(HTTPException): imports.fetch_public('https://example.com/')
    assert make.call_count == 1
    assert make.call_args.args[2] == '93.184.216.34'
    connection.close.assert_called()


def test_public_readme_and_explicit_transcript_import(client, monkeypatch):
    register(client)
    data = json.dumps({'encoding':'base64','size':45,'content':base64.b64encode(b'# Project\nThis README describes a useful neural network.').decode()}).encode()
    monkeypatch.setattr(imports, 'fetch_public', lambda *a: ('https://api.github.com/repos/team/repo/readme','application/json',data))
    r = client.post('/api/v1/imports',json={'url':'https://github.com/team/repo','kind':'github'})
    assert r.status_code == 201, r.text
    assert r.json()['source_type'] == 'github'
    body = {'url':'https://www.youtube.com/watch?v=abcdefghijk','kind':'youtube'}
    r = client.post('/api/v1/imports',json=body)
    assert r.status_code == 422 and 'Paste' in r.text
    r = client.post('/api/v1/imports',json={**body,'transcript':'This is a user provided transcript about solar energy conversion.'})
    assert r.status_code == 201 and r.json()['source_type'] == 'youtube'


def test_search_filters_apply_before_ranking_and_use_exact_tags(client):
    register(client)
    wanted = note(client, title='Neural experiment', tags=['ai'])
    other = note(client, title='Neural training', tags=['training'])
    collection = client.post('/api/v1/collections',json={'title':'Selected'}).json()['id']
    client.put(f'/api/v1/collections/{collection}/items/{wanted}')
    assert {item['document_id'] for item in client.get('/api/v1/search',params={'q':'neural','tag':'ai'}).json()['items']} == {wanted}
    assert client.get('/api/v1/documents',params={'tag':'ai'}).json()['total'] == 1
    assert {item['document_id'] for item in client.get('/api/v1/search',params={'q':'neural','collection_id':collection}).json()['items']} == {wanted}
    assert client.get('/api/v1/search',params={'q':'neural','kind':'file'}).json()['items'] == []
    assert client.get('/api/v1/search',params={'q':'neural','format':'pdf'}).json()['items'] == []
    assert client.get('/api/v1/search',params={'q':'neural','date_from':'2099-01-01'}).json()['items'] == []
    assert client.get('/api/v1/search',params={'q':'neural','date_from':'2026-02-30'}).status_code == 422
    assert client.get('/api/v1/search',params={'q':'neural','date_from':'2026-02-02','date_to':'2025-01-01'}).status_code == 422
    assert client.get('/api/v1/search',params={'q':'neural','collection_id':'unknown'}).status_code == 404


def test_export_archive_includes_originals_and_no_auth_material(client):
    register(client)
    note_id = note(client)
    original = b'A private original containing solar energy research.'
    file_id = client.post('/api/v1/uploads',files={'file':('research.txt',original)}).json()['id']
    response = client.get('/api/v1/export/archive')
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        manifest = json.loads(bundle.read('memoryvault.json'))
        assert {doc['id'] for doc in manifest['documents']} == {note_id,file_id}
        entry = next(item for item in manifest['originals'] if item['document_id'] == file_id)
        assert bundle.read(entry['path']) == original
        assert 'password' not in manifest['profile']
        assert 'sessions' not in manifest and 'auth_tokens' not in manifest


def test_note_quota_and_all_edit_conflicts(client, monkeypatch):
    import app.quota as quota
    register(client)
    monkeypatch.setattr(quota,'QUOTA_BYTES',10)
    assert client.post('/api/v1/notes',json={'title':'Too large','content':'x'*11}).status_code == 413
    monkeypatch.setattr(quota,'QUOTA_BYTES',100000)
    doc_id = note(client)
    old = client.get('/api/v1/documents/'+doc_id).json()
    change = {'title':'Renamed','content':old['content'],'tags':['new'],'version':old['version']}
    r = client.patch('/api/v1/documents/'+doc_id,json=change)
    assert r.status_code == 200, r.text
    assert r.json()['version'] == old['version']+1
    assert client.patch('/api/v1/documents/'+doc_id,json=change).status_code == 409
