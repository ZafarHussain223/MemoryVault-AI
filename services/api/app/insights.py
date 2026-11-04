"""Provider-backed knowledge tools with validated, owned source references."""
import hashlib
import json
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictInt, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from .db import User, Document, Chunk, Insight, Quiz, QuizAttempt, Contradiction, Event, get_db, now
from .security import current_user, owned, rate_limit
from .ai import generate, capabilities
from . import ai_schemas

router = APIRouter(prefix='/api/v1', tags=['knowledge-tools'])
DISCLAIMER = 'Potential conflicts are AI interpretations. Compare the quoted sources and their dates before drawing conclusions.'


class Entity(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=50)


class InsightOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=2500)
    detailed_summary: str = Field(min_length=1, max_length=6500)
    key_points: list[str] = Field(min_length=1, max_length=12)
    categories: list[str] = Field(default_factory=list, max_length=8)
    entities: list[Entity] = Field(default_factory=list, max_length=20)
    sources: list[StrictInt] = Field(min_length=1, max_length=12)


class QuizQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_answer: StrictInt
    explanation: str = Field(min_length=1, max_length=2000)
    source: StrictInt


class AttemptInput(BaseModel):
    answers: list[StrictInt] = Field(min_length=1, max_length=10)


class CompareInput(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=4)


class ConflictOutput(BaseModel):
    source_a: StrictInt
    source_b: StrictInt
    quote_a: str = Field(min_length=8, max_length=1500)
    quote_b: str = Field(min_length=8, max_length=1500)
    explanation: str = Field(min_length=1, max_length=2000)


class ReviewInput(BaseModel):
    status: Literal['dismissed', 'reviewed']


def parse_json(answer):
    try:
        text = answer.strip()
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text, count=1).removesuffix('```').strip()
        return json.loads(text)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(502, 'The AI returned invalid structured content. Please retry.')


def source_chunks(db, doc, limit=8):
    if doc.status != 'ready':
        raise HTTPException(409, 'Wait until this document finishes processing.')
    chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.ordinal).limit(limit)))
    if not chunks:
        raise HTTPException(422, 'This document has no indexed content to analyze.')
    return [{'chunk_id': c.id, 'document_id': doc.id, 'document_version': doc.version,
             'title': doc.title, 'text': c.text, 'page': c.page, 'kind': doc.kind} for c in chunks]


def valid_reference(number, sources):
    if type(number) is not int or not 1 <= number <= len(sources):
        raise HTTPException(502, 'The AI returned an unsupported source reference. Please retry.')
    return sources[number - 1]


def check_versions(db, user, sources):
    from .quota import lock_vault
    lock_vault(db, user.id)
    # A generation can outlive an edit or deletion in another browser tab.
    for doc_id, version in {(s['document_id'], s['document_version']) for s in sources}:
        doc = db.scalar(select(Document).where(Document.id == doc_id, Document.user_id == user.id).execution_options(populate_existing=True))
        if not doc or doc.version != version or doc.status != 'ready':
            raise HTTPException(409, 'A source changed during generation. Refresh and try again.')


def insight_json(row, doc):
    return {'id': row.id, 'document_id': row.document_id, 'document_version': row.document_version,
            **row.payload, 'created': row.created, 'model': row.model, 'stale': row.document_version != doc.version}


@router.get('/documents/{document_id}/insights')
def read_insight(document_id: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    doc = owned(db, Document, document_id, user)
    row = db.scalar(select(Insight).where(Insight.document_id == doc.id, Insight.user_id == user.id))
    return {'insight': insight_json(row, doc) if row else None}


@router.post('/documents/{document_id}/insights')
async def make_insight(document_id: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    rate_limit('ai:' + user.id, 15)
    doc = owned(db, Document, document_id, user)
    sources = source_chunks(db, doc)
    answer = await generate('Analyze these document excerpts and identify the important ideas.', sources,
        'Return only one JSON object with summary, detailed_summary, key_points (array of strings), categories '
        '(up to 8 short suggested tags), entities (array of {name,type}), sources (integer source numbers supporting '
        'the summary). Use only supplied excerpts. Clearly limit conclusions to these excerpts; do not imply the '
        'entire document was reviewed. Never invent entities or facts. Keep all fields concise.',
        response_format=ai_schemas.insight(len(sources)))
    try:
        parsed = InsightOutput.model_validate(parse_json(answer))
        if any(not p.strip() or len(p) > 1000 for p in parsed.key_points):
            raise ValueError()
        citations = [valid_reference(i, sources) for i in dict.fromkeys(parsed.sources)]
        payload = parsed.model_dump(exclude={'sources'})
        payload['categories'] = list(dict.fromkeys(t.strip().lower()[:50] for t in parsed.categories if t.strip()))
        payload['citations'] = citations
        payload['coverage'] = f'Based on the first {len(sources)} indexed excerpts. AI interpretation; verify against the source.'
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(502, 'The AI returned invalid insight content. Please retry.')
    check_versions(db, user, sources)
    row = db.scalar(select(Insight).where(Insight.document_id == doc.id))
    if row is None:
        row = Insight(user_id=user.id, document_id=doc.id)
        db.add(row)
    row.document_version, row.payload, row.model, row.created = doc.version, payload, capabilities()['model'], now()
    db.add(Event(user_id=user.id, kind='insight', text='Insights generated for ' + doc.title))
    db.commit()
    return {'insight': insight_json(row, doc)}


@router.post('/documents/{document_id}/insights/apply-tags')
def apply_tags(document_id: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    from .quota import lock_vault
    lock_vault(db, user.id)
    doc = owned(db, Document, document_id, user)
    row = db.scalar(select(Insight).where(Insight.document_id == doc.id, Insight.user_id == user.id))
    if not row:
        raise HTTPException(404, 'Generate insights first.')
    if doc.status != 'ready' or row.document_version != doc.version:
        raise HTTPException(409, 'These suggestions are outdated. Generate fresh insights first.')
    doc.tags = list(dict.fromkeys(doc.tags + row.payload.get('categories', [])))[:30]
    doc.version += 1
    doc.updated = now()
    row.document_version = doc.version
    db.commit()
    return {'ok': True, 'tags': doc.tags, 'version': doc.version}


def attempt_json(row, quiz, include_results=False):
    result = {'id': row.id, 'score': row.score, 'total': len(quiz.questions), 'created': row.created}
    if include_results:
        result['results'] = [{**q, 'selected': row.answers[i], 'correct': row.answers[i] == q['correct_answer']}
                             for i, q in enumerate(quiz.questions)]
    return result


def quiz_json(db, row):
    doc = db.get(Document, row.document_id)
    attempts = list(db.scalars(select(QuizAttempt).where(QuizAttempt.quiz_id == row.id, QuizAttempt.user_id == row.user_id).order_by(QuizAttempt.created.desc())))
    return {'id': row.id, 'document_id': row.document_id, 'title': row.title, 'created': row.created,
            'stale': not doc or doc.version != row.document_version,
            'questions': [{k: q[k] for k in ['question', 'options', 'citation']} for q in row.questions],
            'attempts': [attempt_json(a, row) for a in attempts]}


@router.get('/quizzes')
def quizzes(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    return [quiz_json(db, q) for q in db.scalars(select(Quiz).where(Quiz.user_id == user.id).order_by(Quiz.created.desc()).limit(100))]


@router.post('/quizzes/{document_id}', status_code=201)
async def make_quiz(document_id: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    rate_limit('ai:' + user.id, 15)
    doc = owned(db, Document, document_id, user)
    sources = source_chunks(db, doc)
    answer = await generate('Create up to five useful multiple-choice questions from these excerpts.', sources,
        'Return only a JSON array. Each object must have question (string), options (array of four distinct '
        'strings), correct_answer (zero-based integer option index), explanation (string), source (integer '
        'source number). Every correct answer and explanation must follow from its cited excerpt. If there '
        'is insufficient material return an empty array. Do not invent information. Keep questions and explanations concise.',
        response_format=ai_schemas.quiz(len(sources)))
    try:
        raw = parse_json(answer)
        if not isinstance(raw, list) or not 1 <= len(raw) <= 10:
            raise ValueError()
        questions = []
        for entry in raw:
            q = QuizQuestion.model_validate(entry)
            if not 0 <= q.correct_answer < len(q.options) or len(set(q.options)) != len(q.options):
                raise ValueError()
            if any(not o.strip() or len(o) > 1000 for o in q.options):
                raise ValueError()
            questions.append({**q.model_dump(exclude={'source'}), 'citation': valid_reference(q.source, sources)})
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(502, 'The AI could not produce a valid grounded quiz from these excerpts. Please retry or choose a richer source.')
    check_versions(db, user, sources)
    quiz = Quiz(user_id=user.id, document_id=doc.id, document_version=doc.version, title=doc.title, questions=questions)
    db.add(quiz)
    db.commit()
    return quiz_json(db, quiz)


@router.post('/quizzes/{quiz_id}/attempts', status_code=201)
def submit_attempt(quiz_id: str, body: AttemptInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    rate_limit('study-attempt:' + user.id, 60)
    quiz = owned(db, Quiz, quiz_id, user)
    doc = owned(db, Document, quiz.document_id, user)
    if doc.status != 'ready' or doc.version != quiz.document_version:
        raise HTTPException(409, 'The source changed. Generate a fresh quiz before submitting answers.')
    if len(body.answers) != len(quiz.questions) or any(not 0 <= a < len(q['options']) for a, q in zip(body.answers, quiz.questions)):
        raise HTTPException(422, 'Choose one valid answer for every question.')
    score = sum(a == q['correct_answer'] for a, q in zip(body.answers, quiz.questions))
    attempt = QuizAttempt(user_id=user.id, quiz_id=quiz.id, answers=body.answers, score=score)
    db.add(attempt)
    db.commit()
    return attempt_json(attempt, quiz, True)


@router.get('/quizzes/{quiz_id}/attempts')
def quiz_attempts(quiz_id: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    quiz = owned(db, Quiz, quiz_id, user)
    return [attempt_json(a, quiz, True) for a in db.scalars(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.user_id == user.id).order_by(QuizAttempt.created.desc()))]


def conflict_json(db, row):
    a, b = db.get(Document, row.document_a), db.get(Document, row.document_b)
    return {k: getattr(row, k) for k in ['id', 'document_a', 'document_b', 'explanation', 'evidence_a', 'evidence_b', 'status', 'created']} | {
        'stale': not a or not b or a.version != row.version_a or b.version != row.version_b}


@router.get('/contradictions')
def conflicts(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    rows = db.scalars(select(Contradiction).where(Contradiction.user_id == user.id).order_by(Contradiction.created.desc()).limit(100))
    return {'items': [conflict_json(db, row) for row in rows], 'disclaimer': DISCLAIMER}


@router.post('/contradictions')
async def compare_sources(body: CompareInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    rate_limit('ai:' + user.id, 15)
    ids = list(dict.fromkeys(body.document_ids))
    if len(ids) < 2:
        raise HTTPException(422, 'Choose at least two different documents.')
    sources = []
    for doc_id in ids:
        sources.extend(source_chunks(db, owned(db, Document, doc_id, user), limit=3))
    answer = await generate('Compare these excerpts for conflicting explicit dates, quantities, or opposing factual statements about the same named subject.', sources,
        'Return only a JSON array with up to five potential conflicts. Each object has source_a and source_b '
        '(integer source numbers from DIFFERENT documents), quote_a and quote_b (exact verbatim substrings '
        'from those excerpts, at least 8 characters), and explanation (why they may conflict, acknowledging '
        'that differences in date or scope may explain them). Return [] when no concrete conflict is supported. '
        'Do not treat differences of topic, missing detail, speculation, or simple restatements as contradictions.',
        response_format=ai_schemas.conflicts(len(sources)))
    try:
        raw = parse_json(answer)
        if not isinstance(raw, list) or len(raw) > 5:
            raise ValueError()
        prepared = []
        for entry in raw:
            item = ConflictOutput.model_validate(entry)
            a, b = valid_reference(item.source_a, sources), valid_reference(item.source_b, sources)
            if a['document_id'] == b['document_id']:
                raise ValueError()
            normalize = lambda text: ' '.join(text.split())
            if normalize(item.quote_a) not in normalize(a['text']) or normalize(item.quote_b) not in normalize(b['text']):
                raise ValueError()
            # Canonical source ordering makes repeated analysis idempotent.
            if a['document_id'] > b['document_id']:
                a, b = b, a
                quote_a, quote_b = item.quote_b, item.quote_a
            else:
                quote_a, quote_b = item.quote_a, item.quote_b
            identity = hashlib.sha256(json.dumps([user.id, a['document_id'], b['document_id'], a['document_version'], b['document_version'], normalize(quote_a), normalize(quote_b)]).encode()).hexdigest()
            prepared.append((identity, a, b, quote_a, quote_b, item.explanation))
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(502, 'The AI comparison did not contain verifiable source quotes. Nothing was saved; please retry.')
    check_versions(db, user, sources)
    saved = []
    for identity, a, b, quote_a, quote_b, explanation in prepared:
        row = db.get(Contradiction, identity)
        if row is None:
            row = Contradiction(id=identity, user_id=user.id, document_a=a['document_id'], document_b=b['document_id'],
                version_a=a['document_version'], version_b=b['document_version'], explanation=explanation,
                evidence_a={**a, 'quote': quote_a}, evidence_b={**b, 'quote': quote_b})
            db.add(row)
        saved.append(row)
    db.commit()
    return {'items': [conflict_json(db, row) for row in saved], 'disclaimer': DISCLAIMER,
            'coverage': 'Compared up to three indexed excerpts per selected document. This is a focused check, not an exhaustive review.'}


@router.patch('/contradictions/{conflict_id}')
def review_conflict(conflict_id: str, body: ReviewInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    row = owned(db, Contradiction, conflict_id, user)
    row.status = body.status
    db.commit()
    return {'ok': True}
