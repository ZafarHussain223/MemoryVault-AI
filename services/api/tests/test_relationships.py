"""Persistence, graph evidence, duplicate and tenant boundaries for manual links."""
from fastapi.testclient import TestClient
from test_workflows import client, database, register, note
from app.main import app


def test_manual_relationship_persists_in_graph_and_can_be_removed(client):
    register(client)
    a = note(client, title='Linear algebra', tags=['math'])
    b = note(client, title='Neural networks', tags=['ai'])
    response = client.post('/api/v1/relationships', json={'source_id':a,'target_id':b,'kind':'prerequisite','note':'Review matrix multiplication first.'})
    assert response.status_code == 201, response.text
    row = response.json()
    assert row['source_id'] == a and row['source_title'] == 'Linear algebra'
    assert row['target_id'] == b and row['kind'] == 'prerequisite'
    assert client.get('/api/v1/relationships').json() == [row]
    edge = next(e for e in client.get('/api/v1/graph').json()['edges'] if e['id'] == row['id'])
    assert edge['source'] == a and edge['target'] == b
    assert edge['manual'] and edge['type'] == 'prerequisite'
    assert edge['note'] == 'Review matrix multiplication first.'
    assert client.delete('/api/v1/relationships/'+row['id']).status_code == 200
    assert client.get('/api/v1/relationships').json() == []
    assert client.get('/api/v1/graph').json()['edges'] == []


def test_relationship_validation_duplicates_and_cascade(client):
    register(client)
    a, b = note(client, title='First'), note(client, title='Second')
    assert client.post('/api/v1/relationships',json={'source_id':a,'target_id':a,'kind':'related'}).status_code == 422
    assert client.post('/api/v1/relationships',json={'source_id':a,'target_id':b,'kind':'made_up'}).status_code == 422
    assert client.post('/api/v1/relationships',json={'source_id':a,'target_id':b,'kind':'related'}).status_code == 201
    assert client.post('/api/v1/relationships',json={'source_id':b,'target_id':a,'kind':'related'}).status_code == 409
    assert client.post('/api/v1/relationships',json={'source_id':a,'target_id':b,'kind':'references'}).status_code == 201
    assert client.post('/api/v1/relationships',json={'source_id':b,'target_id':a,'kind':'references'}).status_code == 201
    client.delete('/api/v1/documents/'+a)
    assert client.get('/api/v1/relationships').json() == []


def test_relationships_cannot_link_or_revoke_another_users_records(client):
    register(client)
    a, b = note(client), note(client, title='Second memory')
    link = client.post('/api/v1/relationships',json={'source_id':a,'target_id':b}).json()
    with TestClient(app) as other:
        register(other,'bob@example.com')
        own = note(other)
        assert other.get('/api/v1/relationships').json() == []
        assert other.post('/api/v1/relationships',json={'source_id':own,'target_id':a}).status_code == 404
        assert other.delete('/api/v1/relationships/'+link['id']).status_code == 404
        assert other.get('/api/v1/graph').json()['edges'] == []
    assert len(client.get('/api/v1/relationships').json()) == 1
