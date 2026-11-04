"""Account-scoped reminders, measured activity and explainable rediscovery."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, delete, func, true
from sqlalchemy.orm import Session
from .db import (User, Document, Collection, Relationship, Event, Reminder, DocumentVisit,
                 Study, Quiz, QuizAttempt, get_db, now)
from .security import current_user, owned, rate_limit
from .quota import lock_vault

router = APIRouter(prefix='/api/v1')
U = Annotated[User, Depends(current_user)]
D = Annotated[Session, Depends(get_db)]


def utc_now():
    return datetime.now(timezone.utc)


class NotificationPreferences(BaseModel):
    processing: bool = True
    reminders: bool = True
    recall: bool = True


def notification_preferences(user):
    return NotificationPreferences.model_validate(user.preferences.get('notifications', {})).model_dump()


@router.get('/notification-preferences')
def get_notification_preferences(user: U):
    return notification_preferences(user)


@router.put('/notification-preferences')
def save_notification_preferences(body: NotificationPreferences, user: U, db: D):
    lock_vault(db, user.id)
    db.refresh(user)
    user.preferences = {**user.preferences, 'notifications': body.model_dump()}
    db.commit()
    return body.model_dump()


class ReminderInput(BaseModel):
    document_id: str | None = None
    title: str = Field(min_length=1, max_length=160)
    due_at: datetime

    @field_validator('title')
    @classmethod
    def title_valid(cls, value):
        if not value.strip():
            raise ValueError('Enter a reminder title.')
        return value.strip()

    @field_validator('due_at')
    @classmethod
    def due_valid(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Include a timezone in the reminder time.')
        value = value.astimezone(timezone.utc)
        if not utc_now() < value <= utc_now() + timedelta(days=366):
            raise ValueError('Choose a future reminder time within the next year.')
        return value


class ReminderEdit(BaseModel):
    document_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    due_at: datetime | None = None
    status: Literal['pending', 'done'] | None = None

    @field_validator('title')
    @classmethod
    def title_valid(cls, value):
        if value is None:
            raise ValueError('Title cannot be empty.')
        return ReminderInput.title_valid(value)

    @field_validator('due_at')
    @classmethod
    def due_valid(cls, value):
        if value is None:
            raise ValueError('Reminder time cannot be empty.')
        return ReminderInput.due_valid(value)


def reminder_json(row):
    return {key: getattr(row, key) for key in ['id', 'document_id', 'title', 'due_at', 'status', 'notified_at', 'created']}


@router.get('/reminders')
def reminders(user: U, db: D):
    return [reminder_json(row) for row in db.scalars(select(Reminder).where(
        Reminder.user_id == user.id).order_by(Reminder.status.desc(), Reminder.due_at).limit(500))]


@router.post('/reminders', status_code=201)
def create_reminder(body: ReminderInput, user: U, db: D):
    rate_limit('reminder:' + user.id, 30)
    lock_vault(db, user.id)
    if body.document_id:
        owned(db, Document, body.document_id, user)
    count = db.scalar(select(func.count()).select_from(Reminder).where(Reminder.user_id == user.id))
    if count >= 500:
        raise HTTPException(409, 'Remove old reminders before adding more. The limit is 500.')
    row = Reminder(user_id=user.id, document_id=body.document_id, title=body.title, due_at=body.due_at.isoformat())
    db.add(row)
    db.commit()
    return reminder_json(row)


@router.patch('/reminders/{reminder_id}')
def edit_reminder(reminder_id: str, body: ReminderEdit, user: U, db: D):
    lock_vault(db, user.id)
    row = owned(db, Reminder, reminder_id, user)
    values = body.model_dump(exclude_unset=True)
    if values.get('document_id'):
        owned(db, Document, values['document_id'], user)
    if 'status' in values and values['status'] is None:
        raise HTTPException(422, 'Choose pending or done.')
    if 'due_at' in values:
        values['due_at'] = values['due_at'].isoformat()
        row.notified_at = None
        db.execute(delete(Event).where(Event.id == 'reminder:' + row.id, Event.user_id == user.id))
    for key, value in values.items():
        setattr(row, key, value)
    if row.status == 'done':
        event = db.get(Event, 'reminder:' + row.id)
        if event:
            event.read = 1
    db.commit()
    return reminder_json(row)


@router.delete('/reminders/{reminder_id}')
def delete_reminder(reminder_id: str, user: U, db: D):
    lock_vault(db, user.id)
    row = owned(db, Reminder, reminder_id, user)
    db.execute(delete(Event).where(Event.id == 'reminder:' + row.id, Event.user_id == user.id))
    db.delete(row)
    db.commit()
    return {'ok': True}


def due_reminders(db, user):
    # Requests serialize on the account row, so polling from multiple tabs cannot
    # deliver the same reminder twice. No background email/push is implied.
    if not notification_preferences(user)['reminders']:
        return
    lock_vault(db, user.id)
    db.refresh(user)
    if not notification_preferences(user)['reminders']:
        db.commit()
        return
    timestamp = utc_now().isoformat()
    due = db.scalars(select(Reminder).where(Reminder.user_id == user.id,
        Reminder.status == 'pending', Reminder.due_at <= timestamp, Reminder.notified_at.is_(None)))
    for row in due:
        db.add(Event(id='reminder:' + row.id, user_id=user.id, kind='reminder', text=row.title, created=timestamp))
        row.notified_at = timestamp
    db.commit()


def recall_notice(db, user):
    today = utc_now().date().isoformat()
    if (not user.preferences.get('recall', True) or not notification_preferences(user)['recall']
            or user.preferences.get('recall_notice_day') == today):
        return
    lock_vault(db, user.id)
    db.refresh(user)
    if (not user.preferences.get('recall', True) or not notification_preferences(user)['recall']
            or user.preferences.get('recall_notice_day') == today):
        db.commit()
        return
    notified = user.preferences.get('recall_notice_ids', [])
    suggestions = [row for row in recall(user, db) if row['id'] not in notified]
    if suggestions:
        source = suggestions[0]
        db.add(Event(id='recall:' + today + ':' + source['id'], user_id=user.id, kind='recall',
                     text='Worth revisiting: ' + source['title'] + '. ' + source['reason']))
        user.preferences = {**user.preferences, 'recall_notice_day': today,
                            'recall_notice_ids': (notified + [source['id']])[-500:]}
    db.commit()


@router.get('/notifications')
def notifications(user: U, db: D):
    due_reminders(db, user)
    recall_notice(db, user)
    preferences = notification_preferences(user)
    query = select(Event).where(Event.user_id == user.id, Event.kind != 'search')
    for setting, kinds in [('processing', ['processing']), ('reminders', ['reminder']), ('recall', ['recall', 'relationship'])]:
        if not preferences[setting]:
            query = query.where(Event.kind.not_in(kinds))
    lookup = {r.id: r for r in db.scalars(select(Reminder).where(Reminder.user_id == user.id))}
    result = []
    for event in db.scalars(query.order_by(Event.created.desc()).limit(100)):
        reminder = lookup.get(event.id.removeprefix('reminder:')) if event.kind == 'reminder' else None
        if event.kind == 'reminder' and reminder is None:
            continue
        recall_source = None
        if event.kind == 'recall':
            source_id = event.id.rsplit(':', 1)[-1]
            recall_source = db.scalar(select(Document.id).where(Document.id == source_id, Document.user_id == user.id))
            if recall_source is None:
                continue
        result.append({'id': event.id, 'text': event.text, 'read': bool(event.read), 'created': event.created,
            'kind': event.kind, 'document_id': reminder.document_id if reminder else recall_source,
            'reminder_id': reminder.id if reminder else None})
    return result


class NotificationRead(BaseModel):
    read: bool


@router.patch('/notifications/{event_id}')
def notification_read(event_id: str, body: NotificationRead, user: U, db: D):
    event = owned(db, Event, event_id, user)
    if event.kind == 'search':
        raise HTTPException(404, 'Notification not found.')
    event.read = int(body.read)
    db.commit()
    return {'ok': True}


@router.delete('/notifications/{event_id}')
def delete_notification(event_id: str, user: U, db: D):
    event = owned(db, Event, event_id, user)
    if event.kind == 'search':
        raise HTTPException(404, 'Notification not found.')
    db.delete(event)
    db.commit()
    return {'ok': True}


@router.post('/documents/{document_id}/visit')
def visit_document(document_id: str, user: U, db: D):
    lock_vault(db, user.id)
    owned(db, Document, document_id, user)
    db.refresh(user)
    if not user.preferences.get('history', True):
        return {'recorded': False}
    timestamp = utc_now().isoformat()
    row = db.scalar(select(DocumentVisit).where(DocumentVisit.user_id == user.id,
        DocumentVisit.document_id == document_id, DocumentVisit.day == timestamp[:10]))
    if row:
        # Repeated clicks/network retries within 30 seconds count as one visit.
        if (utc_now() - datetime.fromisoformat(row.last_visited)).total_seconds() >= 30:
            row.count += 1
        row.last_visited = timestamp
    else:
        db.add(DocumentVisit(user_id=user.id, document_id=document_id, day=timestamp[:10], last_visited=timestamp))
    db.commit()
    return {'recorded': True}

@router.get('/analytics')
def analytics(user: U, db: D, days: int = Query(30, ge=30, le=90)):
    if days not in {30, 90}:
        raise HTTPException(422, 'Choose a 30-day or 90-day period.')
    end = utc_now().date()
    start = end - timedelta(days=days - 1)
    cutoff = start.isoformat()
    activity = {str(start + timedelta(days=i)): {'date': str(start + timedelta(days=i)),
        'saved': 0, 'searches': 0, 'visits': 0, 'quiz_attempts': 0} for i in range(days)}

    def group(model, date_column, field, count, *conditions):
        day = func.substr(date_column, 1, 10)
        for key, value in db.execute(select(day, count).where(*conditions, date_column >= cutoff).group_by(day)):
            if key in activity:
                activity[key][field] = value

    group(Document, Document.created, 'saved', func.count(), Document.user_id == user.id)
    group(Event, Event.created, 'searches', func.count(), Event.user_id == user.id, Event.kind == 'search')
    group(DocumentVisit, DocumentVisit.day, 'visits', func.sum(DocumentVisit.count), DocumentVisit.user_id == user.id)
    group(QuizAttempt, QuizAttempt.created, 'quiz_attempts', func.count(), QuizAttempt.user_id == user.id)
    kinds = dict(db.execute(select(Document.kind, func.count()).where(Document.user_id == user.id).group_by(Document.kind)).all())
    totals = {'memories': sum(kinds.values()), 'documents': kinds.get('file', 0), 'notes': kinds.get('note', 0),
        'links': kinds.get('link', 0), 'storage': db.scalar(select(func.coalesce(func.sum(Document.size), 0)).where(Document.user_id == user.id)),
        'collections': db.scalar(select(func.count()).select_from(Collection).where(Collection.user_id == user.id)),
        'relationships': db.scalar(select(func.count()).select_from(Relationship).where(Relationship.user_id == user.id))}
    formats = [{'format': key, 'count': value} for key, value in db.execute(select(Document.format, func.count()).where(
        Document.user_id == user.id).group_by(Document.format).order_by(func.count().desc()))]
    visits = select(DocumentVisit.document_id, func.sum(DocumentVisit.count).label('visits')).where(
        DocumentVisit.user_id == user.id, DocumentVisit.day >= cutoff).group_by(DocumentVisit.document_id).subquery()
    # Expand only saved tag metadata in SQL; never load document bodies for analytics.
    if db.bind.dialect.name == 'postgresql':
        tags = func.json_array_elements_text(Document.tags).table_valued('value').render_derived(name='saved_tags')
    else:
        tags = func.json_each(Document.tags).table_valued('value').alias('saved_tags')
    topics = [{'tag': tag, 'count': count, 'visits': opens} for tag, count, opens in db.execute(
        select(tags.c.value, func.count(), func.coalesce(func.sum(visits.c.visits), 0)).select_from(Document)
        .join(tags, true()).outerjoin(visits, visits.c.document_id == Document.id)
        .where(Document.user_id == user.id).group_by(tags.c.value).order_by(func.count().desc(), tags.c.value).limit(12))]
    study = {'sessions': 0, 'cards_reviewed': 0, 'cards_known': 0, 'quiz_attempts': 0, 'quiz_correct': 0, 'quiz_questions': 0}
    for progress in db.scalars(select(Study.progress).where(Study.user_id == user.id)):
        study['sessions'] += 1
        study['cards_reviewed'] += len(progress)
        study['cards_known'] += sum(value is True for value in progress.values())
    attempts = db.execute(select(func.count(QuizAttempt.id), func.coalesce(func.sum(QuizAttempt.score), 0),
        func.coalesce(func.sum(func.json_array_length(Quiz.questions)), 0)).join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(QuizAttempt.user_id == user.id, Quiz.user_id == user.id)).one()
    study.update(quiz_attempts=attempts[0], quiz_correct=attempts[1], quiz_questions=attempts[2])
    return {'days': days, 'timezone': 'UTC', 'totals': totals, 'activity': list(activity.values()),
        'study': study, 'formats': formats, 'topics': topics, 'history_enabled': user.preferences.get('history', True)}


@router.get('/recall')
def recall(user: U, db: D):
    if not user.preferences.get('recall', True):
        return []
    fields = [Document.id, Document.title, Document.kind, Document.format, Document.tags, Document.status,
        Document.error, Document.size, Document.version, Document.created, Document.updated,
        Document.source_url, Document.source_type, func.substr(Document.content, 1, 200).label('excerpt')]
    docs = [dict(row) for row in db.execute(select(*fields).where(Document.user_id == user.id,
        Document.status == 'ready').order_by(Document.created.desc()).limit(500)).mappings()]
    if not docs:
        return []
    recent_ids = {row['id'] for row in docs[:3]}
    recent_tags = {tag for row in docs[:3] for tag in row['tags']}
    interests = {tag.strip().lower() for tag in user.preferences.get('interests', [])}
    dismissed = set(user.preferences.get('dismissed', []))
    visits = dict(db.execute(select(DocumentVisit.document_id, func.max(DocumentVisit.last_visited)).where(
        DocumentVisit.user_id == user.id).group_by(DocumentVisit.document_id)).all())
    linked = set()
    for a, b in db.execute(select(Relationship.source_id, Relationship.target_id).where(Relationship.user_id == user.id,
        (Relationship.source_id.in_(recent_ids) | Relationship.target_id.in_(recent_ids)))):
        linked.update({a, b} - recent_ids)
    cutoff = (utc_now() - timedelta(days=30)).isoformat()
    recommendations = []
    for doc in docs[3:]:
        if doc['id'] in dismissed:
            continue
        reasons, signals, score = [], [], 0
        common = sorted(recent_tags & set(doc['tags']))
        if common:
            reasons.append('Shares tags with your three newest memories: ' + ', '.join(common))
            signals.append('recent_tags')
            score += 3
        matched = sorted(interests & set(doc['tags']))
        if matched:
            reasons.append('Matches your saved interests: ' + ', '.join(matched))
            signals.append('interests')
            score += 2
        if doc['id'] in linked:
            reasons.append('You connected this memory to one of your three newest items.')
            signals.append('relationship')
            score += 4
        last_opened = visits.get(doc['id'])
        if doc['created'] < cutoff and user.preferences.get('history', True) and (last_opened is None or last_opened < cutoff):
            reasons.append('No recorded visit in the past 30 days.' if last_opened else 'Saved over 30 days ago, with no recorded visits.')
            signals.append('unvisited')
            score += 1
        if reasons:
            recommendations.append((score, doc['created'], {**doc, 'reason': ' '.join(reasons), 'reasons': reasons, 'signals': signals}))
    recommendations.sort(key=lambda item: (-item[0], item[1]))
    return [row[2] for row in recommendations[:12]]
