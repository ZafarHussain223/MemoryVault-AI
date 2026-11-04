"""Operator commands for embedding upgrades and interrupted local ingestion."""
import argparse
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from .db import DB, Document, now
from .processing import process_document
from .embeddings import preflight


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['reindex','recover'])
    args=parser.parse_args()
    if args.command=='recover':
        cutoff=(datetime.now(timezone.utc)-timedelta(minutes=20)).isoformat()
        with DB() as db:
            result=db.execute(update(Document).where(Document.status=='processing',Document.updated<cutoff).values(status='failed',error='Processing was interrupted. Retry this document.',updated=now()))
            db.commit()
            print(f'{result.rowcount} interrupted documents are available to retry.')
        return
    # Verify actual local inference before changing any document state.
    try:
        preflight()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    with DB() as db:
        ids=list(db.scalars(select(Document.id).where(Document.status.in_(['ready','failed']))))
    failures=0
    for index,document_id in enumerate(ids):
        with DB() as db:
            claim=db.execute(update(Document).where(Document.id==document_id,Document.status.in_(['ready','failed'])).values(status='pending',error='',updated=now()))
            db.commit()
        if not claim.rowcount:continue
        process_document(document_id)
        with DB() as db:
            doc=db.get(Document,document_id)
            failed=bool(doc and doc.status=='failed')
            failures+=int(failed)
        print(f'Indexed {index+1}/{len(ids)}; failures: {failures}',flush=True)
    if failures:raise SystemExit('Some documents failed. Check the vault and retry after correcting configuration.')


if __name__=='__main__':main()
