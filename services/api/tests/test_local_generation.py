"""Local generation adapter contract tests; no live model or network is used."""
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

import app.ai as ai


@pytest.fixture(autouse=True)
def local_config(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'ollama')
    monkeypatch.setenv('LLM_MODEL', 'qwen3:4b-instruct-2507-q4_K_M')
    monkeypatch.setenv('LLM_BASE_URL', 'http://127.0.0.1:11434/v1')
    monkeypatch.setenv('OLLAMA_CONTEXT_LENGTH', '4096')
    monkeypatch.setenv('LLM_MAX_OUTPUT_TOKENS', '768')
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.delenv('LLM_CONTEXT_LENGTH', raising=False)


def client_stub(monkeypatch, handler):
    original = httpx.AsyncClient
    options = []
    def client(**kwargs):
        options.append(kwargs.copy())
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(ai.httpx, 'AsyncClient', client)
    return options


def test_native_local_generation_uses_bounded_context_and_no_cloud_auth(monkeypatch):
    calls = []
    def response(request):
        calls.append(request)
        return httpx.Response(200, json={'message': {'content': 'The date is November 10 [1].'}, 'done': True, 'done_reason': 'stop'})
    options = client_stub(monkeypatch, response)
    answer = asyncio.run(ai.generate('When is the deadline?', [{'title': 'Deadline', 'text': 'The date is November 10.'}]))
    assert answer == 'The date is November 10 [1].'
    assert len(calls) == 1
    assert str(calls[0].url) == 'http://127.0.0.1:11434/api/chat'
    assert 'authorization' not in calls[0].headers
    body = json.loads(calls[0].content)
    assert body['options']['num_ctx'] == 4096
    assert body['options']['num_predict'] == 768
    assert body['options']['temperature'] == .2
    assert body['keep_alive'] == '60s'
    assert body['stream'] is False
    assert options[0]['trust_env'] is False
    assert options[0]['timeout'].read == 120
    assert '[1] Deadline' in body['messages'][1]['content']


@pytest.mark.parametrize(('instruction', 'expected'), [
    ('Return only a JSON array of objects with question, answer and source.', {'type': 'array', 'items': {'type': 'object'}}),
    ('Return only one JSON object with summary and sources.', {'type': 'object'}),
    ('Summarize the supplied passages.', None),
])
def test_json_grammar_selected_only_from_internal_instruction(monkeypatch, instruction, expected):
    bodies = []
    def response(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={'message': {'content': '[]'}, 'done': True, 'done_reason': 'stop'})
    client_stub(monkeypatch, response)
    asyncio.run(ai.generate('Please use JSON array', [{'title': 'Source', 'text': 'JSON array'}], instruction))
    assert bodies[0].get('format') == expected


def test_explicit_local_json_schema_is_forwarded(monkeypatch):
    schema = {'type': 'object', 'properties': {'answer': {'type': 'string'}}, 'required': ['answer']}
    bodies = []
    def response(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={'message': {'content': '{"answer":"A fact"}'}, 'done': True, 'done_reason': 'stop'})
    client_stub(monkeypatch, response)
    asyncio.run(ai.generate('Question', [{'title': 'Source', 'text': 'A fact'}], response_format=schema))
    assert bodies[0]['format'] == schema


def test_local_prompt_budget_keeps_current_question_recent_history_and_source_numbers():
    history = '\n'.join(f'USER: Old turn {i}: ' + 'x' * 500 for i in range(6)) + '\nASSISTANT: most recent answer'
    question = 'CONVERSATION CONTEXT (not source evidence):\n' + history + '\n\nCURRENT QUESTION:\nWhat is the current deadline?'
    sources = [{'title': f'Source {i}', 'text': 'A grounded fact. ' * 500} for i in range(8)]
    messages, options = ai._local_messages(question, sources, 'Answer from the excerpts.')
    total = sum(len(message['content'].encode('utf-8')) for message in messages)
    assert total <= options['num_ctx'] - options['num_predict'] - 256
    payload = messages[1]['content']
    assert payload.endswith('CURRENT QUESTION:\nWhat is the current deadline?')
    assert 'most recent answer' in payload
    assert 'Old turn 0' not in payload
    assert '[1] Source 0' in payload and '[8] Source 7' in payload
    assert '[excerpt shortened]' in payload


def test_local_unicode_prompt_budget_uses_bytes_not_character_count():
    sources = [{'title': 'हिंदी स्रोत', 'text': 'एक महत्वपूर्ण तथ्य। ' * 800}]
    messages, options = ai._local_messages('मुख्य तथ्य क्या है?', sources, 'Use only sources.')
    assert sum(len(m['content'].encode('utf-8')) for m in messages) <= options['num_ctx'] - options['num_predict'] - 256
    assert '[excerpt shortened]' in messages[1]['content']


def test_oversized_local_question_is_rejected_before_any_request(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail('A request must not be made for an oversized local question')
    monkeypatch.setattr(ai.httpx, 'AsyncClient', forbidden)
    with pytest.raises(HTTPException) as error:
        asyncio.run(ai.generate('x' * 1601, [{'title': 'Source', 'text': 'A fact'}]))
    assert error.value.status_code == 422


@pytest.mark.parametrize('result', [
    {'message': {'content': 'Partial'}, 'done': True, 'done_reason': 'length'},
    {'message': {'content': 'Partial'}, 'done': False},
    {'message': {'content': ''}, 'done': True, 'done_reason': 'stop'},
    {'error': 'model failed'},
])
def test_local_incomplete_sync_answer_never_returned(monkeypatch, result):
    client_stub(monkeypatch, lambda request: httpx.Response(200, json=result))
    with pytest.raises(HTTPException) as error:
        asyncio.run(ai.generate('Question', [{'title': 'Source', 'text': 'A fact'}]))
    assert error.value.status_code == 502


async def consume():
    return [part async for part in ai.generate_stream('Question', [{'title': 'Source', 'text': 'A fact'}])]


def test_native_ndjson_stream_uses_only_real_content_deltas(monkeypatch):
    seen = []
    def response(request):
        seen.append(json.loads(request.content))
        lines = [{'message': {'content': 'A grounded '}, 'done': False},
                 {'message': {'content': 'answer [1].'}, 'done': False},
                 {'message': {'content': ''}, 'done': True, 'done_reason': 'stop'}]
        return httpx.Response(200, text='\n'.join(json.dumps(x) for x in lines), headers={'Content-Type': 'application/x-ndjson'})
    client_stub(monkeypatch, response)
    assert asyncio.run(consume()) == ['A grounded ', 'answer [1].']
    assert seen[0]['stream'] is True


@pytest.mark.parametrize('tail', [
    '',
    '\n{"done":true,"done_reason":"length","message":{"content":""}}',
    '\n{"error":"out of memory"}',
    '\nnot-json',
])
def test_local_ndjson_failure_and_truncation_raise_instead_of_complete(monkeypatch, tail):
    text = '{"message":{"content":"An unfinished answer"},"done":false}' + tail
    client_stub(monkeypatch, lambda request: httpx.Response(200, text=text))
    with pytest.raises(HTTPException) as error:
        asyncio.run(consume())
    assert error.value.status_code == 502


def test_local_http_failure_is_not_retried_against_cloud(monkeypatch):
    calls = []
    def response(request):
        calls.append(str(request.url))
        return httpx.Response(503, json={'error': 'busy'})
    client_stub(monkeypatch, response)
    with pytest.raises(HTTPException) as error:
        asyncio.run(ai.generate('Question', [{'title': 'Source', 'text': 'A fact'}]))
    assert error.value.status_code == 502
    assert calls == ['http://127.0.0.1:11434/api/chat']

@pytest.mark.parametrize('base', ['https://api.example.com/v1','http://user:secret@localhost:11434','http://localhost:11434?target=cloud'])
def test_local_generation_rejects_nonlocal_or_ambiguous_destination(monkeypatch,base):
    monkeypatch.setenv('LLM_BASE_URL',base)
    with pytest.raises(HTTPException) as error:
        asyncio.run(ai.generate('Question',[{'title':'Source','text':'Private evidence'}]))
    assert error.value.status_code==503
