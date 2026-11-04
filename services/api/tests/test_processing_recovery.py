"""Regression tests for interrupted workers and parser bounds."""
import io
import sys
import pytest
from sqlalchemy import select, delete
from test_workflows import client, database, register, note
from app import processing
from app.db import DB, Document, Chunk, Event, now

@pytest.mark.parametrize('late_failure', [False, True])
def test_superseded_worker_cannot_replace_retry_result(client, monkeypatch, late_failure):
    register(client)
    document_id = note(client)
    with DB() as db:
        db.get(Document, document_id).status = 'pending'
        db.execute(delete(Event))
        db.commit()
    calls = 0
    winning_chunks = []
    def interrupted_embed(texts):
        nonlocal calls
        calls += 1
        if calls == 1:
            # A recovery/retry completes while the original request is in flight.
            with DB() as db:
                doc = db.get(Document, document_id)
                doc.status, doc.updated = 'pending', now()
                db.commit()
            processing.process_document(document_id)
            with DB() as db:
                winning_chunks.extend(db.scalars(select(Chunk.id).where(Chunk.document_id == document_id)))
            if late_failure:
                raise ValueError('The old request failed after the retry finished.')
        return [None] * len(texts)
    monkeypatch.setattr(processing, 'embed', interrupted_embed)
    processing.process_document(document_id)
    with DB() as db:
        doc = db.get(Document, document_id)
        assert doc.status == 'ready' and doc.error == ''
        assert list(db.scalars(select(Chunk.id).where(Chunk.document_id == document_id))) == winning_chunks
        events = list(db.scalars(select(Event)))
        assert len(events) == 1 and 'ready to search' in events[0].text
    assert calls == 2

def test_duplicate_delivery_does_not_start_second_worker(client, monkeypatch):
    register(client)
    document_id = note(client)
    with DB() as db:
        db.get(Document, document_id).status = 'pending'
        db.commit()
    calls = []
    def embed(texts):
        calls.append(texts)
        processing.process_document(document_id)
        return [None] * len(texts)
    monkeypatch.setattr(processing, 'embed', embed)
    processing.process_document(document_id)
    assert len(calls) == 1
    assert client.get('/api/v1/documents/' + document_id).json()['status'] == 'ready'

def test_incomplete_embeddings_keep_existing_chunks(client, monkeypatch):
    register(client)
    document_id = note(client)
    with DB() as db:
        before = list(db.scalars(select(Chunk.id)))
        db.get(Document, document_id).status = 'pending'
        db.commit()
    monkeypatch.setattr(processing, 'embed', lambda texts: [])
    processing.process_document(document_id)
    with DB() as db:
        assert db.get(Document, document_id).status == 'failed'
        assert list(db.scalars(select(Chunk.id))) == before

def test_core_pdf_keeps_page_numbers_across_blank_page(monkeypatch):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    monkeypatch.setitem(sys.modules, 'pymupdf', None)
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 72 720 Td (Text after a blank page.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    pages = processing.extract(output.getvalue(), 'pdf')
    assert pages[0] == (1, '')
    assert pages[1][0] == 2 and 'Text after a blank page' in pages[1][1]

def test_enqueue_timeout_cannot_overwrite_a_completed_worker(client, monkeypatch):
    from types import SimpleNamespace
    register(client)
    document_id=note(client)
    with DB() as db:
        db.get(Document,document_id).status='pending'
        db.commit()
    class AcceptedQueue:
        def __init__(self,*args,**kwargs):pass
        def enqueue(self,*args,**kwargs):
            with DB() as db:
                doc=db.get(Document,document_id)
                doc.status,doc.error='ready',''
                db.commit()
            raise RuntimeError('Acknowledgement was lost after acceptance.')
    monkeypatch.setattr(processing,'REDIS_URL','redis://test.invalid')
    monkeypatch.setitem(sys.modules,'redis',SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *args:object())))
    monkeypatch.setitem(sys.modules,'rq',SimpleNamespace(Queue=AcceptedQueue,Retry=lambda **kwargs:object()))
    processing.enqueue(document_id,None)
    with DB() as db:
        doc=db.get(Document,document_id)
        assert doc.status=='ready' and doc.error==''
