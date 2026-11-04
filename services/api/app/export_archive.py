"""Private, complete portable exports, including the original uploaded bytes."""
import json
import re
import tempfile
import zipfile
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, Document, User, Collection, Membership, Conversation, Message, get_db, now
from .config import DATA_DIR
from .security import current_user, rate_limit
from .quota import lock_vault
from . import storage
from .profile import ProfileImage

router = APIRouter(prefix='/api/v1')


def rows(db, table, condition):
    return [dict(row) for row in db.execute(select(table).where(condition)).mappings()]


@router.get('/export/archive')
def archive(user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]):
    rate_limit('export:'+user.id, 3)
    # Keep originals and metadata consistent while assembling the archive.
    lock_vault(db, user.id)
    docs = list(db.scalars(select(Document).where(Document.user_id == user.id)))
    collection_ids = select(Collection.id).where(Collection.user_id == user.id)
    conversation_ids = select(Conversation.id).where(Conversation.user_id == user.id)
    data = {
        'schema_version': 1, 'exported_at': now(),
        'profile': {'id': user.id, 'email': user.email, 'name': user.name, 'preferences': user.preferences, 'created': user.created},
        'documents': [{column.name: getattr(doc, column.name) for column in Document.__table__.columns if column.name != 'key'} for doc in docs],
        'collections': rows(db, Collection.__table__, Collection.user_id == user.id),
        'collection_items': rows(db, Membership.__table__, Membership.collection_id.in_(collection_ids)),
        'conversations': rows(db, Conversation.__table__, Conversation.user_id == user.id),
        'messages': rows(db, Message.__table__, Message.conversation_id.in_(conversation_ids)),
        'originals': [],
    }
    # Explicit table allowlist prevents credentials or future confidential server
    # configuration from accidentally entering an export.
    for name in ['events', 'study_sessions', 'document_insights', 'quizzes', 'quiz_attempts', 'contradictions', 'relationships', 'reminders', 'document_visits']:
        table = Base.metadata.tables.get(name)
        if table is not None and 'user_id' in table.c:
            data[name] = rows(db, table, table.c.user_id == user.id)
    export_dir = DATA_DIR / 'exports'
    export_dir.mkdir(parents=True, exist_ok=True)
    output = tempfile.SpooledTemporaryFile(max_size=8*1024*1024, mode='w+b', dir=export_dir)
    try:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            photo = db.get(ProfileImage, user.id)
            if photo:
                bundle.writestr('profile/photo.jpg', photo.content)
                data['profile']['photo'] = {'path': 'profile/photo.jpg', 'updated': photo.updated}
            for doc in docs:
                title = re.sub(r'[^\w. -]', '_', doc.title).strip(' .')[:100] or 'memory'
                filename = 'originals/'+doc.id+'/'+title
                if not doc.key:
                    filename += '.md'
                bundle.writestr(filename, storage.get(doc.key) if doc.key else doc.content.encode('utf-8'))
                data['originals'].append({'document_id': doc.id, 'path': filename})
            bundle.writestr('memoryvault.json', json.dumps(data, ensure_ascii=False, indent=2))
            bundle.writestr('README.txt', 'MemoryVault export\nAll records belong to the exporting account. Original files are under originals/.\nAI insights are generated interpretations; see source references and document versions.\nSession tokens, passwords, authentication tokens and embedding vectors are excluded.\n')
        output.seek(0)
        db.commit()
    except Exception:
        output.close()
        db.rollback()
        raise HTTPException(503, 'The archive could not be assembled. Check storage availability and retry; no data was changed.')

    def stream():
        try:
            while chunk := output.read(65536):
                yield chunk
        finally:
            output.close()
    return StreamingResponse(stream(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename=memoryvault-export.zip'})
