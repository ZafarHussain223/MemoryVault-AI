"""Complete document extraction with bounded, atomic embedding ingestion."""
import io
import json
import logging
import os
import re
import tempfile
from sqlalchemy import delete, insert, select, update
from .db import DB, Document, Chunk, Event, now
from .config import REDIS_URL, DATA_DIR
from . import config, storage
from .embeddings import embed, embedding_model, model_identity
from .document_formats import ALLOWED, validate, extract_other, checked_pages


def extract(data: bytes, extension: str):
    if extension == 'pdf':
        try:
            import pymupdf
        except ImportError:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValueError('Remove the PDF password before uploading it.')
            if len(reader.pages) > config.MAX_DOCUMENT_PAGES:
                raise ValueError(f'Limit: {config.MAX_DOCUMENT_PAGES:,} pages per document. The original is preserved.')
            result, total = [], 0
            for index, page in enumerate(reader.pages):
                text = page.extract_text() or ''
                stream = page.get_contents()
                if len(page.images) or (not text.strip() and stream is not None and stream.get_data().strip()):
                    raise ValueError('This PDF contains pages that need OCR. Install PyMuPDF and Tesseract to index every page.')
                total += len(text)
                if total > config.MAX_EXTRACTED_CHARS:
                    raise ValueError(f'Extracted PDF text exceeds {config.MAX_EXTRACTED_CHARS:,} characters. The original is preserved; nothing was partially indexed.')
                result.append((index + 1, text))
            return checked_pages(result)
        with pymupdf.open(stream=data, filetype='pdf') as pdf:
            if pdf.needs_pass:
                raise ValueError('Remove the PDF password before uploading it.')
            if len(pdf) > config.MAX_DOCUMENT_PAGES:
                raise ValueError(f'Limit: {config.MAX_DOCUMENT_PAGES:,} pages per document. The original is preserved.')
            result, scanned, total = [], 0, 0
            for index, page in enumerate(pdf):
                text = page.get_text(sort=True)
                # A scan may have a native-text page number or header. OCR all
                # pages with displayed raster images, including inline images;
                # otherwise that small text layer can hide the scanned body.
                # Blank pages retain their number without consuming OCR work.
                if page.get_image_info() or (not text.strip() and page.get_drawings()):
                    scanned += 1
                    if scanned > config.MAX_OCR_PAGES:
                        raise ValueError(f'PDF exceeds the configured {config.MAX_OCR_PAGES:,} OCR-page limit. The original is preserved; nothing was partially indexed.')
                    from PIL import Image
                    from .ocr import read_image
                    scale = min(2, 2500 / max(page.rect.width, page.rect.height))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    recognized = read_image(Image.open(io.BytesIO(pix.tobytes('png'))))
                    if text.strip():
                        native = re.sub(r'\s+', ' ', text).strip().casefold()
                        extra = [line for line in recognized.splitlines()
                                 if line.strip() and re.sub(r'\s+', ' ', line).strip().casefold() not in native]
                        if extra:text += '\n' + '\n'.join(extra)
                    else:text = recognized
                total += len(text)
                if total > config.MAX_EXTRACTED_CHARS:
                    raise ValueError(f'Extracted PDF text exceeds {config.MAX_EXTRACTED_CHARS:,} characters. The original is preserved; nothing was partially indexed.')
                result.append((index + 1, text))
            return checked_pages(result)
    if extension in {'png', 'jpg', 'jpeg', 'webp'}:
        from PIL import Image
        from .ocr import read_image
        return checked_pages([(None, read_image(Image.open(io.BytesIO(data))))])
    return extract_other(data, extension)


def chunk_text(text: str, size: int = 1200, overlap: int = 160):
    if size < 2 or overlap < 0 or overlap >= size // 2:
        raise ValueError('Invalid chunk size or overlap.')
    text = text.replace(chr(0), '').strip()
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(' ', start + size // 2, end)
            if boundary > start: end = boundary
        yield text[start:end]
        if end == len(text): break
        start = end - overlap


def process_document(document_id: str):
    claim_time = now()
    with DB() as db:
        claimed = db.execute(update(Document).where(
            Document.id == document_id,
            Document.status.in_(['pending', 'failed']),
        ).values(status='processing', updated=claim_time))
        db.commit()
        if not claimed.rowcount: return
        doc = db.get(Document, document_id)
        if not doc: return
        version, kind, content, key, extension = doc.version, doc.kind, doc.content, doc.key, doc.format
        user_id, title = doc.user_id, doc.title

    def still_owned():
        return (Document.id == document_id, Document.version == version,
                Document.status == 'processing', Document.updated == claim_time)

    try:
        pages = [(None, content)] if kind == 'note' else extract(storage.get(key), extension)
        parts = []
        for page, text in pages:
            for part in chunk_text(text):
                if len(parts) >= config.MAX_DOCUMENT_CHUNKS:
                    raise ValueError(f'Document exceeds {config.MAX_DOCUMENT_CHUNKS:,} indexed passages. The original is preserved; nothing was partially indexed.')
                parts.append((page, part))
        # Stage complete vectors privately on disk instead of keeping tens of
        # thousands of Python float arrays in RAM. Old chunks remain untouched
        # until every batch has succeeded and the source version still matches.
        temporary = DATA_DIR / 'processing'
        temporary.mkdir(parents=True, exist_ok=True)
        identity = model_identity()
        with tempfile.TemporaryFile(mode='w+t', encoding='utf-8', dir=temporary) as vectors:
            for offset in range(0, len(parts), 128):
                with DB() as db:
                    if not db.scalar(select(Document.id).where(*still_owned())): return
                batch = parts[offset:offset + 128]
                embedded = embed([text for _, text in batch])
                if len(embedded) != len(batch):
                    raise ValueError('The embedding provider returned incomplete results. Retry indexing; existing passages are preserved.')
                for vector in embedded:
                    vectors.write(json.dumps(vector, allow_nan=False) + '\n')
            vectors.seek(0)
            with DB() as db:
                completed = db.execute(update(Document).where(*still_owned()).values(
                    content='\n\n'.join(text for _, text in pages), status='ready', error='', updated=now()))
                if not completed.rowcount:
                    db.rollback()
                    return
                db.execute(delete(Chunk).where(Chunk.document_id == document_id))
                rows = []
                for ordinal, (page, text) in enumerate(parts):
                    vector = json.loads(vectors.readline())
                    rows.append({'document_id': document_id, 'ordinal': ordinal, 'page': page,
                                 'text': text, 'embedding': vector, 'model': identity if vector else ''})
                    if len(rows) == 128:
                        db.execute(insert(Chunk), rows)
                        rows = []
                if rows: db.execute(insert(Chunk), rows)
                db.add(Event(user_id=user_id, kind='processing', text=f'{title} is ready to search.'))
                db.commit()
    except Exception as exc:
        with DB() as db:
            failed = db.execute(update(Document).where(*still_owned()).values(
                status='failed', updated=now(),
                error=str(exc)[:200] if isinstance(exc, ValueError) else
                'Processing failed. Check parser, embedding model or OCR configuration and retry. The original is preserved.'))
            if not failed.rowcount:
                db.rollback()
                return
            db.add(Event(user_id=user_id, kind='processing', text=f'Processing failed for {title}.'))
            db.commit()
        logging.getLogger(__name__).warning('Processing failed for %s (%s)', document_id, type(exc).__name__)
        if REDIS_URL: raise


def enqueue(document_id, tasks):
    if REDIS_URL:
        from redis import Redis
        from rq import Queue, Retry
        try:
            timeout = int(os.getenv('DOCUMENT_JOB_TIMEOUT_SECONDS', '3600'))
            if not 60 <= timeout <= 86400: raise ValueError('Invalid document job timeout.')
            Queue('ingestion', connection=Redis.from_url(REDIS_URL)).enqueue(
                process_document, document_id, job_timeout=timeout, retry=Retry(max=2, interval=[15, 60]))
        except Exception:
            with DB() as db:
                # An enqueue timeout can happen after Redis accepted the job.
                db.execute(update(Document).where(Document.id == document_id, Document.status == 'pending').values(
                    status='failed', error='Queue unavailable. Retry after Redis is restored.', updated=now()))
                db.commit()
    else:
        tasks.add_task(process_document, document_id)
