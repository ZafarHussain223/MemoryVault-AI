"""Reminder persistence, history privacy, source deletion and measured analytics."""
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_workflows import client, database, register, note
from app.main import app
from app.db import DB, Reminder, Event, User, Document, DocumentVisit, Study, Quiz, QuizAttempt
from app import engagement


def reminder(client, document_id=None):
    result = client.post('/api/v1/reminders', json={'title':'Review chapter one', 'document_id':document_id,
        'due_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    assert result.status_code == 201, result.text
    return result.json()


def make_due(row_id):
    with DB() as db:
        db.get(Reminder,row_id).due_at = (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        db.commit()


def test_reminder_due_once_read_delete_and_reschedule(client):
    register(client)
    doc = note(client)
    row = reminder(client,doc)
    assert row['status']=='pending' and row['notified_at'] is None
    assert not any(n['kind']=='reminder' for n in client.get('/api/v1/notifications').json())
    make_due(row['id'])
    for _ in range(3):
        notifications = [n for n in client.get('/api/v1/notifications').json() if n['kind']=='reminder']
        assert len(notifications)==1
        assert notifications[0]['document_id']==doc and not notifications[0]['read']
    event_id = notifications[0]['id']
    assert client.patch('/api/v1/notifications/'+event_id,json={'read':True}).status_code==200
    assert client.get('/api/v1/notifications').json()[0]['read']
    assert client.delete('/api/v1/notifications/'+event_id).status_code==200
    assert not any(n['kind']=='reminder' for n in client.get('/api/v1/notifications').json())
    result = client.patch('/api/v1/reminders/'+row['id'],json={'due_at':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()})
    assert result.status_code==200 and result.json()['notified_at'] is None
    make_due(row['id'])
    assert len([n for n in client.get('/api/v1/notifications').json() if n['kind']=='reminder'])==1
    assert client.patch('/api/v1/reminders/'+row['id'],json={'status':'done'}).status_code==200
    assert client.get('/api/v1/notifications').json()[0]['read']
    assert client.delete('/api/v1/reminders/'+row['id']).status_code==200
    assert client.get('/api/v1/reminders').json()==[]
    assert not any(n['kind']=='reminder' for n in client.get('/api/v1/notifications').json())


def test_preferences_persist_and_defer_due_reminders(client):
    register(client)
    note(client)
    row=reminder(client)
    make_due(row['id'])
    prefs={'processing':False,'reminders':False,'recall':False}
    assert client.put('/api/v1/notification-preferences',json=prefs).json()==prefs
    assert client.get('/api/v1/notification-preferences').json()==prefs
    assert client.get('/api/v1/notifications').json()==[]
    assert client.get('/api/v1/reminders').json()[0]['notified_at'] is None
    client.put('/api/v1/notification-preferences',json={**prefs,'reminders':True})
    assert len(client.get('/api/v1/notifications').json())==1
    # Saving ordinary settings preserves independently saved notification settings.
    client.put('/api/v1/settings',json={'name':'Alice'})
    assert client.get('/api/v1/notification-preferences').json()['processing'] is False


def test_reminder_timezone_validation_and_tenant_isolation(client):
    register(client)
    doc=note(client)
    row=reminder(client,doc)
    for due in ['2030-01-01T12:00:00','2000-01-01T12:00:00Z','2035-01-01T12:00:00Z']:
        assert client.post('/api/v1/reminders',json={'title':'Review','due_at':due}).status_code==422
    assert client.patch('/api/v1/reminders/'+row['id'],json={'title':' '}).status_code==422
    assert client.patch('/api/v1/reminders/'+row['id'],json={'due_at':None}).status_code==422
    with TestClient(app) as other:
        register(other,'bob@example.com')
        assert other.get('/api/v1/reminders').json()==[]
        assert other.patch('/api/v1/reminders/'+row['id'],json={'status':'done'}).status_code==404
        assert other.delete('/api/v1/reminders/'+row['id']).status_code==404
        assert other.post('/api/v1/reminders',json={'title':'Private','due_at':row['due_at'],'document_id':doc}).status_code==404
        assert other.post('/api/v1/documents/'+doc+'/visit').status_code==404
    make_due(row['id'])
    event=next(n for n in client.get('/api/v1/notifications').json() if n['kind']=='reminder')
    with TestClient(app) as other:
        register(other,'carol@example.com')
        assert other.delete('/api/v1/notifications/'+event['id']).status_code==404
        assert other.patch('/api/v1/notifications/'+event['id'],json={'read':True}).status_code==404


def test_document_deletion_cascades_reminders_visits_and_notification(client):
    register(client)
    doc=note(client)
    row=reminder(client,doc)
    client.post('/api/v1/documents/'+doc+'/visit')
    make_due(row['id'])
    client.get('/api/v1/notifications')
    assert client.delete('/api/v1/documents/'+doc).status_code==200
    assert client.get('/api/v1/reminders').json()==[]
    with DB() as db:
        assert db.scalar(select(DocumentVisit)) is None
        assert db.get(Event,'reminder:'+row['id']) is None


def test_analytics_uses_actual_data_and_history_setting(client):
    user=register(client)['user']['id']
    doc=note(client,tags=['math'])
    client.post('/api/v1/documents/'+doc+'/visit')
    client.post('/api/v1/documents/'+doc+'/visit')
    client.get('/api/v1/search?q=neural')
    with DB() as db:
        db.add(Study(user_id=user,document_id=doc,cards=[{},{}],progress={'0':True,'1':False}))
        quiz=Quiz(user_id=user,document_id=doc,document_version=1,title='Chapter',questions=[{},{}]);db.add(quiz);db.flush()
        db.add(QuizAttempt(user_id=user,quiz_id=quiz.id,answers=[0,1],score=1));db.commit()
    result=client.get('/api/v1/analytics?days=30')
    assert result.status_code==200,result.text
    result=result.json()
    assert result['totals']['notes']==1 and result['totals']['memories']==1
    assert len(result['activity'])==30
    assert result['activity'][-1]=={'date':datetime.now(timezone.utc).date().isoformat(),'saved':1,'searches':1,'visits':1,'quiz_attempts':1}
    assert result['study']=={'sessions':1,'cards_reviewed':2,'cards_known':1,'quiz_attempts':1,'quiz_correct':1,'quiz_questions':2}
    assert result['topics']==[{'tag':'math','count':1,'visits':1}]
    client.put('/api/v1/settings',json={'name':'Alice','history':False})
    assert client.post('/api/v1/documents/'+doc+'/visit').json()=={'recorded':False}
    client.get('/api/v1/search?q=weights')
    assert client.get('/api/v1/analytics').json()['activity'][-1]['searches']==1
    client.delete('/api/v1/history')
    result=client.get('/api/v1/analytics').json()
    assert result['activity'][-1]['searches']==0 and result['activity'][-1]['visits']==0
    assert not result['history_enabled']
    with TestClient(app) as other:
        register(other,'bob@example.com')
        isolated=other.get('/api/v1/analytics?days=90').json()
        assert isolated['totals']['memories']==0 and isolated['topics']==[]
        assert isolated['study']['quiz_attempts']==0 and len(isolated['activity'])==90


def test_recall_explains_interests_links_neglect_and_respects_settings(client):
    user=register(client)['user']['id']
    old=note(client,title='Old math',tags=['math'])
    for title in ['Fresh one','Fresh two','Fresh three']:
        latest=note(client,title=title,tags=['new'])
    with DB() as db:
        db.get(Document,old).created=(datetime.now(timezone.utc)-timedelta(days=60)).isoformat()
        db.get(User,user).preferences={'history':True,'recall':True,'interests':['math']};db.commit()
    client.post('/api/v1/relationships',json={'source_id':old,'target_id':latest,'kind':'related'})
    rows=client.get('/api/v1/recall').json()
    assert rows[0]['id']==old and set(rows[0]['signals'])=={'interests','relationship','unvisited'}
    client.post('/api/v1/documents/'+old+'/visit')
    assert 'unvisited' not in client.get('/api/v1/recall').json()[0]['signals']
    client.post('/api/v1/recall/'+old+'/dismiss')
    assert client.get('/api/v1/recall').json()==[]
    client.put('/api/v1/settings',json={'name':'Alice','recall':False})
    assert client.get('/api/v1/recall').json()==[]


def test_export_contains_only_owned_reminders_and_visits(client):
    register(client)
    doc=note(client)
    row=reminder(client,doc)
    client.post('/api/v1/documents/'+doc+'/visit')
    with TestClient(app) as other:
        register(other,'bob@example.com');reminder(other)
    result=client.get('/api/v1/export/archive')
    assert result.status_code==200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        data=json.loads(archive.read('memoryvault.json'))
    assert len(data['reminders'])==1 and data['reminders'][0]['id']==row['id']
    assert len(data['document_visits'])==1 and data['document_visits'][0]['document_id']==doc

def test_recall_notice_is_grounded_throttled_and_respects_opt_out(client, monkeypatch):
    register(client)
    originals=[note(client,title='Earlier source '+str(i),tags=['research']) for i in range(2)]
    for i in range(3):note(client,title='Recent source '+str(i),tags=['research'])
    prefs={'processing':False,'reminders':True,'recall':False}
    client.put('/api/v1/notification-preferences',json=prefs)
    assert client.get('/api/v1/notifications').json()==[]
    client.put('/api/v1/notification-preferences',json={**prefs,'recall':True})
    notices=client.get('/api/v1/notifications').json()
    assert len(notices)==1 and notices[0]['kind']=='recall'
    assert notices[0]['document_id'] in originals
    assert 'Shares tags' in notices[0]['text']
    client.delete('/api/v1/notifications/'+notices[0]['id'])
    assert client.get('/api/v1/notifications').json()==[]
    tomorrow=datetime.now(timezone.utc)+timedelta(days=1)
    monkeypatch.setattr(engagement,'utc_now',lambda:tomorrow)
    second=client.get('/api/v1/notifications').json()
    assert len(second)==1 and second[0]['document_id']!=notices[0]['document_id']
    client.delete('/api/v1/documents/'+second[0]['document_id'])
    assert client.get('/api/v1/notifications').json()==[]


def test_reminder_offset_normalizes_and_unsupported_analytics_range_rejected(client):
    register(client)
    due=(datetime.now(timezone.utc)+timedelta(days=1)).astimezone(timezone(timedelta(hours=5,minutes=30)))
    result=client.post('/api/v1/reminders',json={'title':'Timezone check','due_at':due.isoformat()})
    assert result.status_code==201
    stored=datetime.fromisoformat(result.json()['due_at'])
    assert stored.utcoffset()==timedelta(0) and stored==due
    for days in [0,31,60,91]:
        assert client.get('/api/v1/analytics',params={'days':days}).status_code==422
