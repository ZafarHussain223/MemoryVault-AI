"""Deterministic contracts for local embeddings; no model download or live server."""
import json
import math
import sys

import httpx
import pytest
from sqlalchemy import select

from app import embeddings, maintenance, processing, search
from app.db import DB, Chunk, Document
from test_workflows import client, database, register, note


@pytest.fixture
def local_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, 'EMBEDDINGS', 'ollama')
    monkeypatch.setattr(embeddings, 'EMBED_MODEL', 'qwen3-embedding:0.6b')
    for name in ['EMBEDDING_MODEL_REVISION', 'EMBEDDING_BASE_URL', 'EMBEDDING_BATCH_SIZE', 'EMBEDDING_TIMEOUT_SECONDS', 'EMBEDDING_DIMENSIONS']:
        monkeypatch.delenv(name, raising=False)
    return embeddings


def mock_service(monkeypatch, handler):
    original = httpx.Client
    seen = []
    def client_factory(**kwargs):
        seen.append(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(embeddings.httpx, 'Client', client_factory)
    return seen


def vector(value=1):
    return [value] + [0] * 383


def test_ollama_batches_documents_normalizes_and_keeps_text_local(local_embeddings, monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json={'embeddings': [vector(4) for _ in body['input']]})
    clients = mock_service(monkeypatch, respond)
    rows = embeddings.embed(['Passage '+str(i) for i in range(17)])
    assert len(rows) == 17
    assert all(len(row) == 384 and math.isclose(sum(v*v for v in row), 1) for row in rows)
    bodies = [json.loads(r.content) for r in requests]
    assert [len(b['input']) for b in bodies] == [8, 8, 1]
    assert bodies[0]['input'][0] == 'Passage 0'
    assert all(b['dimensions'] == 384 and b['keep_alive'] == 0 and b['truncate'] is False for b in bodies)
    assert all(str(r.url) == 'http://127.0.0.1:11434/api/embed' for r in requests)
    assert clients[0]['trust_env'] is False and clients[0]['follow_redirects'] is False


def test_query_instruction_is_only_applied_to_query(local_embeddings, monkeypatch):
    bodies = []
    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={'embeddings':[vector()]})
    mock_service(monkeypatch, respond)
    embeddings.embed(['How do plants make food?'], query=True)
    embeddings.embed(['Leaves capture sunlight.'])
    assert bodies[0]['input'][0] == 'Instruct: '+embeddings.QUERY_INSTRUCTION+'\nQuery:How do plants make food?'
    assert bodies[1]['input'] == ['Leaves capture sunlight.']


@pytest.mark.parametrize('payload', [
    {'embeddings':[]}, {'embeddings':[vector(), vector()]}, {'embeddings':[[1.0]*1024]},
    {'embeddings':[[0.0]*384]}, {'embeddings':[['bad']*384]}, {'embeddings':[[True]*384]},
    {'embeddings':None}, {},
])
def test_invalid_vectors_rejected_without_partial_results(local_embeddings, monkeypatch, payload):
    mock_service(monkeypatch, lambda request:httpx.Response(200, json=payload))
    with pytest.raises(ValueError, match='Local embeddings'):
        embeddings.embed(['A document passage.'])


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_vectors_rejected(value):
    with pytest.raises(ValueError, match='Local embeddings'):
        embeddings._normalize(vector(value))


def test_provider_error_does_not_expose_response_details(local_embeddings, monkeypatch):
    mock_service(monkeypatch, lambda request:httpx.Response(500, text='private source and server credentials'))
    with pytest.raises(ValueError) as error:
        embeddings.embed(['A private passage.'])
    assert 'private' not in str(error.value) and 'credentials' not in str(error.value)


@pytest.mark.parametrize('endpoint', ['https://example.com', 'http://127.0.0.1:11434/redirect', 'http://user:password@localhost:11434', 'http://localhost:11434?target=cloud'])
def test_embedding_endpoint_rejects_nonlocal_or_ambiguous_destinations(local_embeddings, monkeypatch, endpoint):
    monkeypatch.setenv('EMBEDDING_BASE_URL', endpoint)
    with pytest.raises(ValueError, match='local Ollama HTTP origin'):
        embeddings.embed(['A private passage.'])


def test_dimension_change_needs_explicit_schema_migration(local_embeddings, monkeypatch):
    monkeypatch.setenv('EMBEDDING_DIMENSIONS', '1024')
    with pytest.raises(ValueError, match='requires 384'):
        embeddings.embed(['A passage.'])


def test_identity_tracks_model_revision_and_query_contract(local_embeddings, monkeypatch):
    original = embeddings.model_identity()
    assert 'qwen3-embedding:0.6b' in original and ':d384:' in original and embeddings.QUERY_VERSION in original
    monkeypatch.setenv('EMBEDDING_MODEL_REVISION', 'sha256:revision-two')
    assert embeddings.model_identity() != original
    monkeypatch.setattr(embeddings, 'EMBEDDINGS', 'sentence-transformers')
    monkeypatch.setattr(embeddings, 'EMBED_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
    assert embeddings.model_identity() == 'sentence-transformers/all-MiniLM-L6-v2'


def test_disabled_backend_preserves_keyword_mode(monkeypatch):
    monkeypatch.setattr(embeddings, 'EMBEDDINGS', 'disabled')
    assert not embeddings.enabled()
    assert embeddings.embed(['A note.']) == [None]
    assert embeddings.embed([]) == []


def test_semantic_retrieval_is_owner_scoped_and_excludes_incompatible_vectors(client, monkeypatch):
    user = register(client)
    first = note(client, title='Garden journal', content='Leaves capture sunlight and manufacture sugar.')
    second = note(client, title='Old model source', content='An older source was indexed differently.')
    with DB() as db:
        owner = db.get(Document, first).user_id
        for chunk in db.scalars(select(Chunk)):
            chunk.embedding = vector()
            chunk.model = 'local-current' if chunk.document_id == first else 'incompatible-old'
        db.commit()
    monkeypatch.setattr(search, 'embeddings_enabled', lambda:True)
    monkeypatch.setattr(search, 'model_identity', lambda:'local-current')
    calls = []
    def query_embed(texts, *, query=False):
        calls.append((texts, query))
        return [vector()]
    monkeypatch.setattr(search, 'embed', query_embed)
    with DB() as db:
        result = search.retrieve(db, owner, 'photosynthesis')
        assert [row['document_id'] for row in result] == [first]
        assert search.retrieve(db, 'someone-else', 'photosynthesis') == []
    assert all(query for _, query in calls)


def test_reindex_preflight_failure_preserves_ready_documents(client, monkeypatch):
    register(client)
    doc_id = note(client)
    with DB() as db:
        prior = [(c.id, c.text) for c in db.scalars(select(Chunk))]
    def unavailable():
        raise ValueError('Local model is unavailable.')
    monkeypatch.setattr(maintenance, 'preflight', unavailable)
    monkeypatch.setattr(sys, 'argv', ['maintenance', 'reindex'])
    with pytest.raises(SystemExit, match='unavailable'):
        maintenance.main()
    with DB() as db:
        assert db.get(Document, doc_id).status == 'ready'
        assert [(c.id, c.text) for c in db.scalars(select(Chunk))] == prior


def test_indexing_stores_current_embedding_identity(client, monkeypatch):
    register(client)
    monkeypatch.setattr(processing, 'embed', lambda texts:[vector() for _ in texts])
    monkeypatch.setattr(processing, 'model_identity', lambda:'ollama:test-model:d384:saved-passages-v1')
    doc_id = note(client, title='Fresh embedded note', content='A valid model identity accompanies the saved vector.')
    with DB() as db:
        chunk = db.scalar(select(Chunk).where(Chunk.document_id == doc_id))
        assert chunk.model == 'ollama:test-model:d384:saved-passages-v1'
        assert len(chunk.embedding) == 384

@pytest.mark.parametrize('actual', ['a'*64, 'b'*64, None])
def test_pinned_revision_is_verified_before_private_text_is_sent(local_embeddings, monkeypatch, actual):
    monkeypatch.setenv('EMBEDDING_MODEL_REVISION', 'sha256:'+'a'*64)
    sent=[]
    def response(request):
        sent.append(request)
        if request.url.path == '/api/tags':
            rows=[] if actual is None else [{'model':embeddings.EMBED_MODEL,'digest':actual}]
            return httpx.Response(200,json={'models':rows})
        return httpx.Response(200,json={'embeddings':[vector()]})
    mock_service(monkeypatch,response)
    if actual=='a'*64:
        assert len(embeddings.embed(['A private passage.'])[0])==384
        assert len(sent)==2
    else:
        with pytest.raises(ValueError,match='Local embeddings'):
            embeddings.embed(['A private passage.'])
        assert [r.method for r in sent]==['GET']
