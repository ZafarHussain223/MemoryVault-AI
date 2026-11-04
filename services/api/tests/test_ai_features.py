"""Deterministic verification of grounded generation and account controls."""
import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_workflows import client, database, register, note
from app.main import app
from app.db import DB, Document, Insight, Quiz, QuizAttempt, Contradiction, Conversation
import app.main as main
import app.insights as insights
import app.ai as ai


def stub_generation(monkeypatch, payload):
    async def generate(*args, **kwargs):
        return json.dumps(payload)
    monkeypatch.setattr(insights, 'generate', generate)


def insight_payload():
    return {'summary': 'Neural networks learn patterns.', 'detailed_summary': 'These excerpts describe adjusting weights to learn patterns.',
            'key_points': ['Weights are adjusted.'], 'categories': ['Machine Learning'],
            'entities': [{'name': 'Neural networks', 'type': 'concept'}], 'sources': [1]}


def quiz_payload():
    return [{'question': 'What changes during learning?', 'options': ['Weights', 'File names', 'Page numbers', 'Dates'],
             'correct_answer': 0, 'explanation': 'The source states that weights are adjusted.', 'source': 1},
            {'question': 'What do neural networks learn?', 'options': ['Filenames', 'Patterns'],
             'correct_answer': 1, 'explanation': 'Patterns are described in the source.', 'source': 1}]


def test_insights_persist_and_apply_categories(client, monkeypatch):
    register(client)
    document_id = note(client)
    assert client.get(f'/api/v1/documents/{document_id}/insights').json() == {'insight': None}
    stub_generation(monkeypatch, insight_payload())
    result = client.post(f'/api/v1/documents/{document_id}/insights')
    assert result.status_code == 200, result.text
    row = result.json()['insight']
    assert row['citations'][0]['document_id'] == document_id
    assert row['categories'] == ['machine learning']
    assert not row['stale']
    applied = client.post(f'/api/v1/documents/{document_id}/insights/apply-tags')
    assert applied.status_code == 200
    assert set(applied.json()['tags']) == {'ai', 'machine learning'}
    doc = client.get(f'/api/v1/documents/{document_id}').json()
    assert client.patch(f'/api/v1/documents/{document_id}', json={'title': 'Renamed', 'content': doc['content'], 'version': doc['version']}).status_code == 200
    assert client.get(f'/api/v1/documents/{document_id}/insights').json()['insight']['stale']
    assert client.post(f'/api/v1/documents/{document_id}/insights/apply-tags').status_code == 409


def test_insights_reject_invalid_sources_and_changed_documents(client, monkeypatch):
    register(client)
    document_id = note(client)
    payload = insight_payload()
    payload['sources'] = [99]
    stub_generation(monkeypatch, payload)
    assert client.post(f'/api/v1/documents/{document_id}/insights').status_code == 502
    assert client.get(f'/api/v1/documents/{document_id}/insights').json()['insight'] is None
    async def changed_source(*args, **kwargs):
        with DB() as db:
            db.execute(update(Document).where(Document.id == document_id).values(version=Document.version + 1))
            db.commit()
        return json.dumps(insight_payload())
    monkeypatch.setattr(insights, 'generate', changed_source)
    assert client.post(f'/api/v1/documents/{document_id}/insights').status_code == 409
    assert client.get(f'/api/v1/documents/{document_id}/insights').json()['insight'] is None


def test_quiz_answers_hidden_until_scored_and_persisted(client, monkeypatch):
    register(client)
    document_id = note(client)
    stub_generation(monkeypatch, quiz_payload())
    response = client.post('/api/v1/quizzes/' + document_id)
    assert response.status_code == 201, response.text
    quiz = response.json()
    assert 'correct_answer' not in quiz['questions'][0]
    assert 'explanation' not in quiz['questions'][0]
    invalid = client.post(f"/api/v1/quizzes/{quiz['id']}/attempts", json={'answers': [0]})
    assert invalid.status_code == 422
    result = client.post(f"/api/v1/quizzes/{quiz['id']}/attempts", json={'answers': [0, 0]})
    assert result.status_code == 201, result.text
    assert result.json()['score'] == 1 and result.json()['total'] == 2
    assert result.json()['results'][1]['correct_answer'] == 1
    assert result.json()['results'][0]['citation']['document_id'] == document_id
    assert len(client.get(f"/api/v1/quizzes/{quiz['id']}/attempts").json()) == 1
    assert client.get('/api/v1/quizzes').json()[0]['attempts'][0]['score'] == 1
    client.delete('/api/v1/documents/' + document_id)
    assert client.get('/api/v1/quizzes').json() == []
    with DB() as db:
        assert not db.scalars(select(QuizAttempt)).all()


def test_quiz_rejects_invalid_model_answers_and_stale_source(client, monkeypatch):
    register(client)
    document_id = note(client)
    payload = quiz_payload()
    payload[0]['correct_answer'] = 9
    stub_generation(monkeypatch, payload)
    assert client.post('/api/v1/quizzes/' + document_id).status_code == 502
    assert client.get('/api/v1/quizzes').json() == []
    stub_generation(monkeypatch, quiz_payload())
    quiz = client.post('/api/v1/quizzes/' + document_id).json()
    doc = client.get('/api/v1/documents/' + document_id).json()
    client.patch('/api/v1/documents/' + document_id, json={'title': 'New content', 'content': 'Different material', 'version': doc['version']})
    assert client.post(f"/api/v1/quizzes/{quiz['id']}/attempts", json={'answers': [0, 1]}).status_code == 409


def test_conflicts_require_exact_cross_document_evidence(client, monkeypatch):
    register(client)
    a = note(client, title='First deadline', content='The application deadline is November 10.')
    b = note(client, title='Second deadline', content='The application deadline is November 15.')
    payload = [{'source_a': 1, 'source_b': 2, 'quote_a': 'deadline is November 10', 'quote_b': 'deadline is November 15',
                'explanation': 'These deadlines may conflict, although one may be a later revision.'}]
    stub_generation(monkeypatch, payload)
    result = client.post('/api/v1/contradictions', json={'document_ids': [a, b]})
    assert result.status_code == 200, result.text
    row = result.json()['items'][0]
    assert {row['document_a'], row['document_b']} == {a, b}
    assert not row['stale']
    assert client.patch('/api/v1/contradictions/' + row['id'], json={'status': 'reviewed'}).status_code == 200
    assert client.post('/api/v1/contradictions', json={'document_ids': [a, b]}).json()['items'][0]['id'] == row['id']
    assert len(client.get('/api/v1/contradictions').json()['items']) == 1
    payload[0]['quote_a'] = 'deadline is December 10'
    stub_generation(monkeypatch, payload)
    assert client.post('/api/v1/contradictions', json={'document_ids': [a, b]}).status_code == 502
    client.delete('/api/v1/documents/' + a)
    assert client.get('/api/v1/contradictions').json()['items'] == []


def test_knowledge_tools_missing_provider_and_ownership(client, monkeypatch):
    register(client)
    document_id = note(client)
    for route in [f'/documents/{document_id}/insights', '/quizzes/' + document_id]:
        assert client.post('/api/v1' + route).status_code == 503
    stub_generation(monkeypatch, quiz_payload())
    quiz = client.post('/api/v1/quizzes/' + document_id).json()
    with TestClient(app) as other:
        register(other, 'bob@example.com')
        assert other.post('/api/v1/quizzes/' + document_id).status_code == 404
        assert other.get(f'/api/v1/documents/{document_id}/insights').status_code == 404
        assert other.post(f"/api/v1/quizzes/{quiz['id']}/attempts", json={'answers': [0, 1]}).status_code == 404
        assert other.get('/api/v1/quizzes').json() == []


def test_session_revocation_and_password_change(client):
    register(client)
    with TestClient(app) as other:
        result = other.post('/api/v1/auth/login', json={'email': 'alice@example.com', 'password': 'A-secure-test-password'})
        other.headers['X-CSRF-Token'] = result.json()['csrf']
        sessions = client.get('/api/v1/auth/sessions').json()
        assert len(sessions) == 2 and sum(s['current'] for s in sessions) == 1
        other_id = next(s['id'] for s in sessions if not s['current'])
        assert client.delete('/api/v1/auth/sessions/' + other_id).status_code == 200
        assert other.get('/api/v1/auth/me').status_code == 401
    assert client.post('/api/v1/auth/change-password', json={'current_password': 'wrong', 'password': 'A-new-secure-password'}).status_code == 400
    assert client.post('/api/v1/auth/change-password', json={'current_password': 'A-secure-test-password', 'password': 'A-new-secure-password'}).status_code == 200
    assert client.get('/api/v1/auth/me').status_code == 401
    assert client.post('/api/v1/auth/login', json={'email': 'alice@example.com', 'password': 'A-new-secure-password'}).status_code == 200


def test_chat_context_rename_and_regenerate(client, monkeypatch):
    register(client)
    note(client)
    prompts = []
    async def generate(question, sources):
        prompts.append(question)
        return 'Neural networks adjust weights [1].'
    monkeypatch.setattr(main, 'generate', generate)
    monkeypatch.setattr(main, 'capabilities', lambda: {'generation': True})
    first = client.post('/api/v1/chat', json={'question': 'How do neural networks learn?'})
    assert first.status_code == 200, first.text
    cid = first.json()['conversation_id']
    follow = client.post('/api/v1/chat', json={'question': 'Can you explain that again?', 'conversation_id': cid})
    assert follow.status_code == 200, follow.text
    assert 'How do neural networks learn?' in prompts[-1]
    assert client.patch('/api/v1/conversations/' + cid, json={'title': 'Learning review'}).json()['title'] == 'Learning review'
    result = client.post('/api/v1/conversations/' + cid + '/regenerate')
    assert result.status_code == 200, result.text
    messages = client.get('/api/v1/conversations/' + cid).json()
    assert len(messages) == 4
    assert messages[-1]['id'] == follow.json()['message']['id']


def test_stream_success_and_failure_persistence(client, monkeypatch):
    register(client)
    note(client)
    monkeypatch.setattr(main, 'capabilities', lambda: {'generation': True})
    async def stream(question, sources):
        yield 'Weights '
        yield 'change [1].'
    monkeypatch.setattr(main, 'generate_stream', stream)
    result = client.post('/api/v1/chat/stream', json={'question': 'Neural weights?'})
    assert result.status_code == 200
    assert 'event: token' in result.text and 'event: done' in result.text
    conversations = client.get('/api/v1/conversations').json()
    assert len(conversations) == 1
    async def failure(question, sources):
        yield 'Partial'
        raise HTTPException(502, 'Provider failed')
    monkeypatch.setattr(main, 'generate_stream', failure)
    result = client.post('/api/v1/chat/stream', json={'question': 'Neural weights?'})
    assert 'event: error' in result.text and 'event: done' not in result.text
    assert len(client.get('/api/v1/conversations').json()) == 1


def test_chat_rejects_invalid_citations(client, monkeypatch):
    register(client)
    note(client)
    monkeypatch.setattr(main, 'capabilities', lambda: {'generation': True})
    async def bad(*args):
        return 'Unsupported source [99].'
    monkeypatch.setattr(main, 'generate', bad)
    assert client.post('/api/v1/chat', json={'question': 'neural'}).status_code == 502
    assert client.get('/api/v1/conversations').json() == []


def test_openai_sse_parser_uses_provider_deltas(monkeypatch):
    import asyncio
    import httpx
    monkeypatch.setenv('LLM_PROVIDER', 'openai')
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    monkeypatch.setenv('LLM_API_KEY', 'test-only-not-a-secret')
    original = httpx.AsyncClient
    seen = []
    def response(request):
        seen.append(json.loads(request.content))
        body = 'data: {"choices":[{"delta":{"content":"Grounded "}}]}\n\ndata: {"choices":[{"delta":{"content":"answer [1]."}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=body, headers={'Content-Type': 'text/event-stream'})
    monkeypatch.setattr(ai.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(response), **kwargs))
    async def consume():
        return [part async for part in ai.generate_stream('Question', [{'title': 'Source', 'text': 'A fact'}])]
    assert asyncio.run(consume()) == ['Grounded ', 'answer [1].']
    assert seen[0]['stream'] is True


def test_flashcards_validate_citations_and_expire_after_source_edit(client, monkeypatch):
    register(client)
    document_id = note(client)
    async def generate(*args, **kwargs):
        return json.dumps([{'question':'What changes during learning?','answer':'Weights.','source':1}])
    monkeypatch.setattr(main, 'generate', generate)
    result = client.post('/api/v1/study/'+document_id)
    assert result.status_code == 200, result.text
    study = result.json()
    assert not study['stale'] and study['cards'][0]['citation']['document_version'] == 1
    assert client.put(f"/api/v1/study/{study['id']}/progress",json={'card':0,'known':True}).status_code == 200
    doc = client.get('/api/v1/documents/'+document_id).json()
    client.patch('/api/v1/documents/'+document_id,json={'title':'Changed','content':doc['content'],'version':doc['version']})
    assert client.get('/api/v1/study').json()[0]['stale']
    assert client.put(f"/api/v1/study/{study['id']}/progress",json={'card':0,'known':True}).status_code == 409


def test_flashcards_reject_source_changes_during_generation(client, monkeypatch):
    register(client)
    document_id = note(client)
    async def changed(*args, **kwargs):
        with DB() as db:
            db.execute(update(Document).where(Document.id==document_id).values(version=Document.version+1))
            db.commit()
        return json.dumps([{'question':'A question','answer':'An answer','source':1}])
    monkeypatch.setattr(main,'generate',changed)
    assert client.post('/api/v1/study/'+document_id).status_code == 409
    assert client.get('/api/v1/study').json() == []


def test_password_change_invalidates_outstanding_reset_tokens(client):
    import time
    from app.db import AuthToken
    from app.security import hash_token
    register(client)
    user_id = client.get('/api/v1/auth/me').json()['user']['id']
    raw = 'test-reset-token-that-must-be-revoked'
    with DB() as db:
        db.add(AuthToken(token=hash_token(raw),user_id=user_id,kind='reset',expires=int(time.time())+600))
        db.commit()
    assert client.post('/api/v1/auth/change-password',json={'current_password':'A-secure-test-password','password':'A-new-secure-password'}).status_code == 200
    assert client.post('/api/v1/auth/reset-password',json={'token':raw,'password':'Another-secure-password'}).status_code == 400


@pytest.mark.parametrize('stream_body', [
    'data: {"choices":[{"delta":{"content":"An interrupted answer"}}]}\n\n',
    'data: {"choices":[{"delta":{"content":"A truncated answer"},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n',
])
def test_provider_stream_rejects_truncated_output(monkeypatch, stream_body):
    import asyncio
    import httpx
    monkeypatch.setenv('LLM_PROVIDER','openai')
    monkeypatch.setenv('LLM_MODEL','test-model')
    monkeypatch.setenv('LLM_API_KEY','test-only-not-a-secret')
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200,text=stream_body,headers={'Content-Type':'text/event-stream'}))
    monkeypatch.setattr(ai.httpx,'AsyncClient',lambda **kwargs: original(transport=transport,**kwargs))
    async def consume():
        return [part async for part in ai.generate_stream('Question',[{'title':'Source','text':'A fact'}])]
    with pytest.raises(HTTPException) as error:
        asyncio.run(consume())
    assert error.value.status_code == 502


def test_conflict_regeneration_on_new_source_versions_is_fresh(client, monkeypatch):
    register(client)
    a = note(client,title='First deadline',content='The application deadline is November 10.')
    b = note(client,title='Second deadline',content='The application deadline is November 15.')
    payload = [{'source_a':1,'source_b':2,'quote_a':'deadline is November 10','quote_b':'deadline is November 15','explanation':'These may be different revisions.'}]
    stub_generation(monkeypatch,payload)
    first = client.post('/api/v1/contradictions',json={'document_ids':[a,b]}).json()['items'][0]
    doc = client.get('/api/v1/documents/'+a).json()
    client.patch('/api/v1/documents/'+a,json={'title':'Updated first deadline','content':doc['content'],'version':doc['version']})
    second = client.post('/api/v1/contradictions',json={'document_ids':[a,b]}).json()['items'][0]
    assert second['id'] != first['id']
    assert not second['stale']


@pytest.mark.parametrize('route', ['chat', 'chat/stream', 'regenerate'])
def test_slow_local_retrieval_keeps_api_responsive(client, monkeypatch, route):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    register(client)
    document_id = note(client)
    conversation = client.post('/api/v1/chat', json={'question': 'What learns patterns?', 'document_id': document_id}).json()
    entered, release = Event(), Event()
    original = main.retrieve
    def slow_retrieve(*args, **kwargs):
        entered.set()
        assert release.wait(10), 'Test did not release the simulated local embedding call'
        return original(*args, **kwargs)
    monkeypatch.setattr(main, 'retrieve', slow_retrieve)
    path = '/api/v1/conversations/' + conversation['conversation_id'] + '/regenerate' if route == 'regenerate' else '/api/v1/' + route
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(client.post, path, json={'question': 'What learns patterns?', 'document_id': document_id})
        try:
            assert entered.wait(3)
            health = executor.submit(client.get, '/api/v1/health').result(timeout=3)
            assert health.status_code == 200
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200


def test_flashcard_generation_passes_required_fields_and_bounded_sources(client, monkeypatch):
    register(client)
    document_id = note(client)
    captured = {}
    async def constrained(*args, **kwargs):
        captured.update(kwargs['response_format'])
        return json.dumps([{'question': 'What learns patterns?', 'answer': 'Neural networks.', 'source': 1}])
    monkeypatch.setattr(main, 'generate', constrained)
    result = client.post('/api/v1/study/' + document_id)
    assert result.status_code == 200, result.text
    item = captured['items']
    assert set(item['required']) == {'question', 'answer', 'source'}
    assert item['properties']['source'] == {'type': 'integer', 'minimum': 1, 'maximum': 1}
    assert item['additionalProperties'] is False
