"""Owner-scoped hybrid retrieval with filters applied before candidate ranking."""
import math
import re
from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import select, exists, func, or_, and_, cast, Text
from sqlalchemy.orm import load_only
from .db import Chunk, Document, Collection, Membership
from .embeddings import embed, enabled as embeddings_enabled, model_identity


def exact_tag(db, tag):
    if db.bind.dialect.name == 'postgresql':
        values = func.json_array_elements_text(Document.tags).table_valued('value').render_derived(name='tag_values')
    else:
        values = func.json_each(Document.tags).table_valued('value').alias('tag_values')
    return exists(select(1).select_from(values).where(values.c.value == tag))


def filtered_documents(db, user_id, *, kind='', format='', tag='', collection_id='', date_from='', date_to=''):
    query = select(Document.id).where(Document.user_id == user_id)
    if kind:
        if kind not in {'file', 'note', 'link'}:
            raise HTTPException(422, 'Unknown source type.')
        query = query.where(Document.kind == kind)
    if format:
        from .processing import ALLOWED
        if format not in ALLOWED:
            raise HTTPException(422, 'Unknown file format.')
        query = query.where(Document.format == format)
    if len(tag) > 50:
        raise HTTPException(422, 'Tag is too long.')
    if tag:
        query = query.where(exact_tag(db, tag.strip().lower()))
    if collection_id:
        collection = db.scalar(select(Collection).where(Collection.id == collection_id, Collection.user_id == user_id))
        if not collection:
            raise HTTPException(404, 'Collection not found.')
        if collection.rule_tag:
            query = query.where(exact_tag(db, collection.rule_tag))
        else:
            query = query.where(Document.id.in_(select(Membership.document_id).where(Membership.collection_id == collection_id)))
    try:
        start = date.fromisoformat(date_from) if date_from else None
        end = date.fromisoformat(date_to) if date_to else None
        if start and end and start > end:
            raise ValueError()
        if start:
            query = query.where(Document.created >= start.isoformat())
        if end:
            query = query.where(Document.created < (end + timedelta(days=1)).isoformat())
    except (ValueError, OverflowError):
        raise HTTPException(422, 'Use a valid saved-date range in YYYY-MM-DD format.')
    return query


def retrieve(db, user_id, query, document_id=None, limit=8, filters=None):
    tokens = list(dict.fromkeys(re.findall(r'\w+', query.lower())))[:32]
    statement = select(Chunk, Document).join(Document).where(Document.user_id == user_id, Document.status == 'ready')
    if document_id:
        statement = statement.where(Document.id == document_id)
    if filters:
        statement = statement.where(Document.id.in_(filtered_documents(db, user_id, **filters)))
    vector = None
    if embeddings_enabled():
        try:
            vector = embed([query], query=True)[0]
        except Exception:
            raise HTTPException(503, 'Semantic model unavailable. Check the local model installation.')
    identity = model_identity()
    # Stream the full owned candidate set in SQLite. A fixed first-N cutoff
    # made late chapters disappear from semantic search in large books/vaults.
    lexical_terms = []
    for token in tokens:
        pattern = '%' + token.replace('%', '').replace('_', '\\_') + '%'
        lexical_terms.extend([Chunk.text.ilike(pattern, escape='\\'), Document.title.ilike(pattern, escape='\\')])
    conditions = [or_(*lexical_terms)] if lexical_terms else []
    if vector is not None:
        compatible = and_(Chunk.model == identity, Chunk.embedding.is_not(None))
        if db.bind.dialect.name == 'postgresql':
            nearest = statement.with_only_columns(Chunk.id).where(compatible).order_by(Chunk.embedding.cosine_distance(vector)).limit(100)
            conditions.append(Chunk.id.in_(nearest))
        else:
            conditions.append(compatible)
    if not conditions:
        return []
    candidates = statement.where(or_(*conditions)).options(load_only(
        Document.id, Document.title, Document.kind, Document.format,
        Document.version, Document.created, Document.source_url,
    )).execution_options(yield_per=128)
    found = {}
    token_set = set(tokens)
    def order(item):
        return (-item['score'], item['document_id'], item['chunk_id'])
    for chunk, doc in db.execute(candidates):
        words = set(re.findall(r'\w+', (doc.title+' '+chunk.text).lower()))
        lexical = len(token_set & words) / max(1, len(token_set))
        title_match = len(token_set & set(re.findall(r'\w+', doc.title.lower()))) / max(1, len(token_set))
        semantic = 0
        if vector is not None and chunk.embedding is not None and chunk.model == identity and len(vector) == len(chunk.embedding):
            semantic = sum(float(a)*float(b) for a, b in zip(vector, chunk.embedding))
        score = .65*semantic + .3*lexical + .05*title_match if vector is not None else .9*lexical+.1*title_match
        if not math.isfinite(score):
            continue
        if lexical > 0 or (vector is not None and semantic >= .32):
            item = {'chunk_id': chunk.id, 'document_id': doc.id, 'title': doc.title, 'text': chunk.text, 'page': chunk.page, 'score': round(score, 4), 'kind': doc.kind, 'format': doc.format, 'document_version': doc.version, 'created': doc.created, 'source_url': getattr(doc, 'source_url', '')}
            found[chunk.id] = item
            if len(found) > limit:
                worst = max(found.values(), key=order)
                del found[worst['chunk_id']]
    return sorted(found.values(), key=order)
