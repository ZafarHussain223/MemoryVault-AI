import os
from pathlib import Path
os.environ.setdefault('DATABASE_URL', 'sqlite:///./data/test-memoryvault.db')
os.environ.setdefault('DATA_DIR', './data/test-storage')
os.environ.setdefault('EMBEDDING_BACKEND', 'disabled')
os.environ.setdefault('LLM_PROVIDER', 'none')
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,DB,Document,Chunk,Event
from app.security import _buckets
from sqlalchemy import select
@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine);_buckets.clear()
    yield
    Base.metadata.drop_all(engine)
@pytest.fixture
def client():
    with TestClient(app) as c:yield c

def register(client,email='alice@example.com'):
    r=client.post('/api/v1/auth/register',json={'email':email,'password':'A-secure-test-password','name':'Alice'})
    assert r.status_code==201,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf']
    return r.json()
def note(client,title='Neural notes',content='Neural networks learn patterns by adjusting weights.',tags=None):
    r=client.post('/api/v1/notes',json={'title':title,'content':content,'tags':tags or ['ai']})
    assert r.status_code==201,r.text
    return r.json()['id']

def test_register_login_logout(client):
    register(client)
    r=client.get('/api/v1/auth/me');assert r.status_code==200
    assert 'HttpOnly' in str(client.cookies) or client.cookies.get('mv_session')
    assert client.post('/api/v1/auth/logout').status_code==200
    assert client.get('/api/v1/documents').status_code==401
    r=client.post('/api/v1/auth/login',json={'email':'alice@example.com','password':'A-secure-test-password'})
    assert r.status_code==200
    assert 'HttpOnly' in r.headers['set-cookie']

def test_wrong_password(client):
    register(client)
    r=client.post('/api/v1/auth/login',json={'email':'alice@example.com','password':'incorrect-password'})
    assert r.status_code==401

def test_csrf_and_origin(client):
    register(client)
    client.headers.pop('X-CSRF-Token')
    assert client.post('/api/v1/notes',json={'title':'Bad'}).status_code==403
    assert client.post('/api/v1/auth/login',headers={'origin':'https://evil.example'},json={'email':'alice@example.com','password':'A-secure-test-password'}).status_code==403

def test_notes_index_update_and_stale_edit(client):
    register(client);id=note(client)
    doc=client.get('/api/v1/documents/'+id).json();assert doc['status']=='ready'
    results=client.get('/api/v1/search',params={'q':'weights'}).json()['items'];assert results[0]['document_id']==id
    r=client.patch('/api/v1/documents/'+id,json={'title':'Updated','content':'Recursion requires a base case.','tags':['code'],'version':doc['version']})
    assert r.status_code==200
    assert client.get('/api/v1/search?q=weights').json()['items']==[]
    assert client.get('/api/v1/search?q=recursion').json()['items'][0]['document_id']==id
    assert client.patch('/api/v1/documents/'+id,json={'title':'Stale','content':'old','version':doc['version']}).status_code==409

def test_account_isolation(client):
    register(client);id=note(client)
    collection=client.post('/api/v1/collections',json={'title':'Private'}).json()['id']
    chat=client.post('/api/v1/chat',json={'question':'neural'}).json()['conversation_id']
    with TestClient(app) as other:
        register(other,'bob@example.com')
        for url in ['/documents/'+id,'/documents/'+id+'/download','/conversations/'+chat]:assert other.get('/api/v1'+url).status_code==404
        assert other.get('/api/v1/search?q=neural').json()['items']==[]
        assert other.get('/api/v1/documents').json()['total']==0
        assert other.delete('/api/v1/documents/'+id).status_code==404
        assert other.put('/api/v1/collections/'+collection+'/items/'+id).status_code==404
        assert other.post('/api/v1/chat',json={'question':'neural','conversation_id':chat}).status_code==404

def test_upload_download_duplicate_delete(client):
    register(client);payload=b'Solar panels convert sunlight into electricity.'
    r=client.post('/api/v1/uploads',files={'file':('solar.txt',payload,'text/plain')});assert r.status_code==201,r.text
    id=r.json()['id']
    assert client.get('/api/v1/documents/'+id).json()['status']=='ready'
    assert client.get('/api/v1/documents/'+id+'/download').content==payload
    assert client.post('/api/v1/uploads',files={'file':('same.txt',payload)}).status_code==409
    assert client.get('/api/v1/search?q=sunlight').json()['items']
    assert client.delete('/api/v1/documents/'+id).status_code==200
    assert not client.get('/api/v1/search?q=sunlight').json()['items']
    assert client.get('/api/v1/documents/'+id).status_code==404
    with DB() as db:assert not db.scalars(select(Chunk)).all()

def test_invalid_uploads(client):
    register(client)
    for name,content in [('fake.pdf',b'not a pdf'),('script.exe',b'executable'),('bad.json',b'{bad'),('empty.txt',b'')]:
        assert client.post('/api/v1/uploads',files={'file':(name,content)}).status_code==422

def test_pdf_pages_and_extraction(client):
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(612,792)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 72 720 Td (Recursion has a base case.) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    out=io.BytesIO();writer.write(out)
    register(client);r=client.post('/api/v1/uploads',files={'file':('notes.pdf',out.getvalue(),'application/pdf')});assert r.status_code==201
    result=client.get('/api/v1/search?q=recursion').json()['items'][0];assert result['page']==1

def test_collections_and_smart_rules(client):
    register(client);id=note(client)
    c=client.post('/api/v1/collections',json={'title':'Research'}).json()['id']
    assert client.put(f'/api/v1/collections/{c}/items/{id}').status_code==200
    assert client.put(f'/api/v1/collections/{c}/items/{id}').status_code==200
    assert client.get('/api/v1/collections').json()[0]['count']==1
    smart=client.post('/api/v1/collections',json={'title':'AI','rule_tag':'ai'}).json()['id']
    assert client.get('/api/v1/documents?collection_id='+smart).json()['total']==1
    assert client.delete('/api/v1/collections/'+c).status_code==200
    assert client.get('/api/v1/documents/'+id).status_code==200

def test_retrieval_chat_and_source_deletion(client):
    register(client);id=note(client)
    r=client.post('/api/v1/chat',json={'question':'How do neural networks learn?'})
    assert r.status_code==200,r.text
    data=r.json();assert 'Retrieval-only' in data['message']['content']
    assert data['message']['citations'][0]['document_id']==id
    client.delete('/api/v1/documents/'+id)
    messages=client.get('/api/v1/conversations/'+data['conversation_id']).json()
    assert messages[-1]['citations']==[]
    assert 'removed' in messages[-1]['content']

def test_missing_provider_study(client):
    register(client);id=note(client)
    assert client.post('/api/v1/study/'+id).status_code==503

def test_provider_failure_does_not_save_fake_answer(client,monkeypatch):
    from fastapi import HTTPException
    import app.main as main
    register(client);note(client)
    monkeypatch.setattr(main,'capabilities',lambda:{'generation':True})
    async def fail(*args):raise HTTPException(502,'Provider unavailable')
    monkeypatch.setattr(main,'generate',fail)
    assert client.post('/api/v1/chat',json={'question':'neural'}).status_code==502
    assert client.get('/api/v1/conversations').json()==[]

def test_graph_recall_and_preferences(client):
    register(client)
    for i in range(5):note(client,title=f'Note {i}')
    graph=client.get('/api/v1/graph').json();assert len(graph['nodes'])==5 and len(graph['edges'])==10
    recall=client.get('/api/v1/recall').json();assert len(recall)==2
    client.post('/api/v1/recall/'+recall[0]['id']+'/dismiss')
    assert len(client.get('/api/v1/recall').json())==1
    client.put('/api/v1/settings',json={'name':'Alice','history':False,'recall':False})
    client.get('/api/v1/search?q=neural')
    with DB() as db:assert not db.scalars(select(Event).where(Event.kind=='search')).all()
    assert client.get('/api/v1/recall').json()==[]

def test_export_and_account_deletion(client):
    register(client);note(client)
    data=client.get('/api/v1/export').json();assert len(data['documents'])==1
    assert 'password' not in data['profile']
    assert client.delete('/api/v1/account').status_code==200
    assert client.get('/api/v1/auth/me').status_code==401
    with DB() as db:assert not db.scalars(select(Document)).all()

def test_chunker_has_overlap():
    from app.processing import chunk_text
    chunks=list(chunk_text('word '*1000));assert len(chunks)>1
    assert chunks[0][-100:] in chunks[1]

def test_password_reset_and_verification(client):
    import re
    from email import policy
    from email.parser import BytesParser
    from app.config import DATA_DIR
    register(client)
    r=client.post('/api/v1/auth/send-verification');assert r.status_code==200
    mail=max((DATA_DIR/'outbox').glob('*.eml'),key=lambda p:p.stat().st_mtime)
    token=re.search(r'token=([A-Za-z0-9_-]+)',BytesParser(policy=policy.default).parsebytes(mail.read_bytes()).get_content()).group(1)
    assert client.post('/api/v1/auth/verify',json={'token':token}).status_code==200
    assert client.post('/api/v1/auth/verify',json={'token':token}).status_code==400
    assert client.get('/api/v1/auth/me').json()['user']['preferences']['email_verified'] is True
    result=client.post('/api/v1/auth/forgot-password',json={'email':'alice@example.com'})
    missing=client.post('/api/v1/auth/forgot-password',json={'email':'missing@example.com'})
    assert result.json()==missing.json()
    mail=max((DATA_DIR/'outbox').glob('*.eml'),key=lambda p:p.stat().st_mtime)
    token=re.search(r'token=([A-Za-z0-9_-]+)',BytesParser(policy=policy.default).parsebytes(mail.read_bytes()).get_content()).group(1)
    assert client.post('/api/v1/auth/reset-password',json={'token':token,'password':'Another-secure-password'}).status_code==200
    assert client.get('/api/v1/auth/me').status_code==401
    assert client.post('/api/v1/auth/reset-password',json={'token':token,'password':'Another-secure-password'}).status_code==400
    assert client.post('/api/v1/auth/login',json={'email':'alice@example.com','password':'Another-secure-password'}).status_code==200
