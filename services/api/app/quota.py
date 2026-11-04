"""Serialize vault mutations so quota and optimistic version checks cannot race."""
from fastapi import HTTPException
from sqlalchemy import select, update, func
from .db import User, Document
from .config import QUOTA_BYTES


def lock_vault(db, user_id: str) -> None:
    # A no-op write obtains a row lock on PostgreSQL and a writer lock on SQLite.
    # The caller holds it until the document mutation commits or rolls back.
    db.execute(update(User).where(User.id == user_id).values(name=User.name).execution_options(synchronize_session=False))


def check_quota(db, user_id: str, additional_bytes: int) -> None:
    lock_vault(db, user_id)
    used = db.scalar(select(func.coalesce(func.sum(Document.size), 0)).where(Document.user_id == user_id)) or 0
    if used + additional_bytes > QUOTA_BYTES:
        raise HTTPException(413, 'Vault storage limit reached. Delete unused items before adding more.')
