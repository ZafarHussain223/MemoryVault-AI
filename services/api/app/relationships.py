"""Explicit user-authored connections, separate from inferred shared tags."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased
from .db import Document, Relationship, User, get_db
from .security import current_user, owned, rate_limit
from .quota import lock_vault

router = APIRouter(prefix='/api/v1/relationships', tags=['relationships'])
D = Annotated[Session, Depends(get_db)]
U = Annotated[User, Depends(current_user)]
RELATION_LABELS = {'related':'Related to', 'references':'References', 'prerequisite':'Prerequisite for', 'part_of':'Part of'}


class RelationshipInput(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=100)
    kind: Literal['related', 'references', 'prerequisite', 'part_of'] = 'related'
    note: str = Field(default='', max_length=1000)

    @field_validator('note')
    @classmethod
    def clean_note(cls, value):
        return value.strip()


def relationship_json(row, source_title='', target_title=''):
    return {key: getattr(row, key) for key in ['id', 'source_id', 'target_id', 'kind', 'note', 'created']} | {'source_title':source_title, 'target_title':target_title}


@router.get('')
def relationships(user: U, db: D):
    source, target = aliased(Document), aliased(Document)
    statement = select(Relationship, source.title, target.title).join(source, source.id == Relationship.source_id).join(target, target.id == Relationship.target_id).where(Relationship.user_id == user.id, source.user_id == user.id, target.user_id == user.id).order_by(Relationship.created.desc())
    return [relationship_json(row, a, b) for row, a, b in db.execute(statement)]


@router.post('', status_code=201)
def create_relationship(body: RelationshipInput, user: U, db: D):
    rate_limit('relationships:'+user.id, 60)
    lock_vault(db, user.id)
    source = owned(db, Document, body.source_id, user)
    target = owned(db, Document, body.target_id, user)
    if source.id == target.id:
        raise HTTPException(422, 'Choose two different memories to connect.')
    if body.kind == 'related' and source.id > target.id:
        source, target = target, source
    duplicate = db.scalar(select(Relationship.id).where(Relationship.user_id == user.id,
        Relationship.source_id == source.id, Relationship.target_id == target.id, Relationship.kind == body.kind))
    if duplicate:
        raise HTTPException(409, 'This connection already exists.')
    row = Relationship(user_id=user.id, source_id=source.id, target_id=target.id, kind=body.kind, note=body.note)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'The memories changed or this connection already exists. Refresh and try again.')
    return relationship_json(row, source.title, target.title)


@router.delete('/{relationship_id}')
def remove_relationship(relationship_id: str, user: U, db: D):
    lock_vault(db, user.id)
    row = owned(db, Relationship, relationship_id, user)
    db.delete(row)
    db.commit()
    return {'ok': True}
