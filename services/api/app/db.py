from datetime import datetime, timezone
import uuid
from sqlalchemy import create_engine, event, String, Text, Integer, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, mapped_column, sessionmaker
from .config import DATABASE_URL

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
if DATABASE_URL.startswith("postgresql"):
    from pgvector.sqlalchemy import Vector
    embedding_type = Vector(384)
else:
    embedding_type = JSON
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id = mapped_column(String, primary_key=True, default=uid)
    email = mapped_column(String(254), unique=True, index=True)
    password = mapped_column(String)
    name = mapped_column(String(100), default="")
    preferences = mapped_column(JSON, default=lambda: {"history": True, "recall": True, "onboarded": False, "interests": []})
    created = mapped_column(String, default=now)
class Session(Base):
    __tablename__ = "sessions"
    token = mapped_column(String, primary_key=True)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf = mapped_column(String)
    expires = mapped_column(Integer)
class Document(Base):
    __tablename__ = "documents"
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title = mapped_column(String(255))
    kind = mapped_column(String, default="note")
    format = mapped_column(String, default="md")
    source_url = mapped_column(String(2048), default="", server_default="")
    source_type = mapped_column(String(30), default="", server_default="")
    content = mapped_column(Text, default="")
    tags = mapped_column(JSON, default=list)
    status = mapped_column(String, default="pending")
    error = mapped_column(String, default="")
    key = mapped_column(String, default="")
    digest = mapped_column(String, default="")
    size = mapped_column(Integer, default=0)
    version = mapped_column(Integer, default=1)
    created = mapped_column(String, default=now, index=True)
    updated = mapped_column(String, default=now)
class Chunk(Base):
    __tablename__ = "chunks"
    id = mapped_column(String, primary_key=True, default=uid)
    document_id = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    ordinal = mapped_column(Integer)
    page = mapped_column(Integer, nullable=True)
    text = mapped_column(Text)
    embedding = mapped_column(embedding_type, nullable=True)
    model = mapped_column(String, default="")
    __table_args__ = (UniqueConstraint("document_id", "ordinal"),)
class Collection(Base):
    __tablename__ = "collections"
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title = mapped_column(String(100))
    rule_tag = mapped_column(String(50), default="")
    created = mapped_column(String, default=now)
class Membership(Base):
    __tablename__ = "collection_items"
    collection_id = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True)
    document_id = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
class Conversation(Base):
    __tablename__ = "conversations"
    revision = mapped_column(Integer, default=1, server_default="1")
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title = mapped_column(String(100))
    created = mapped_column(String, default=now)
class Message(Base):
    __tablename__ = "messages"
    id = mapped_column(String, primary_key=True, default=uid)
    conversation_id = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role = mapped_column(String)
    content = mapped_column(Text)
    citations = mapped_column(JSON, default=list)
    created = mapped_column(String, default=now)
class Event(Base):
    __tablename__ = "events"
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind = mapped_column(String)
    text = mapped_column(String)
    read = mapped_column(Integer, default=0)
    created = mapped_column(String, default=now)
class Study(Base):
    __tablename__ = "study_sessions"
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    cards = mapped_column(JSON, default=list)
    progress = mapped_column(JSON, default=dict)
    created = mapped_column(String, default=now)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def foreign_keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
DB = sessionmaker(engine, expire_on_commit=False)
def get_db():
    with DB() as db: yield db

class AuthToken(Base):
    __tablename__ = 'auth_tokens'
    token = mapped_column(String, primary_key=True)
    user_id = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind = mapped_column(String)
    expires = mapped_column(Integer)
    used = mapped_column(Integer, default=0)


class Insight(Base):
    __tablename__ = "document_insights"
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    document_version = mapped_column(Integer)
    payload = mapped_column(JSON)
    model = mapped_column(String)
    created = mapped_column(String, default=now)

class Quiz(Base):
    __tablename__ = "quizzes"
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    document_version = mapped_column(Integer)
    title = mapped_column(String(255))
    questions = mapped_column(JSON)
    created = mapped_column(String, default=now)

class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    quiz_id = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    answers = mapped_column(JSON)
    score = mapped_column(Integer)
    created = mapped_column(String, default=now)

class Contradiction(Base):
    __tablename__ = "contradictions"
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_a = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    document_b = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_a = mapped_column(Integer)
    version_b = mapped_column(Integer)
    explanation = mapped_column(Text)
    evidence_a = mapped_column(JSON)
    evidence_b = mapped_column(JSON)
    status = mapped_column(String, default="pending")
    created = mapped_column(String, default=now)

class Relationship(Base):
    __tablename__ = 'relationships'
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    source_id = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    target_id = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = mapped_column(String(30), nullable=False)
    note = mapped_column(String(1000), default='', nullable=False)
    created = mapped_column(String, default=now, nullable=False)
    __table_args__ = (UniqueConstraint('user_id', 'source_id', 'target_id', 'kind', name='uq_relationship_identity'),)

class Reminder(Base):
    __tablename__ = 'reminders'
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    document_id = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), nullable=True, index=True)
    title = mapped_column(String(160), nullable=False)
    due_at = mapped_column(String, nullable=False, index=True)
    status = mapped_column(String(20), default='pending', nullable=False)
    notified_at = mapped_column(String, nullable=True)
    created = mapped_column(String, default=now, nullable=False)

class DocumentVisit(Base):
    __tablename__ = 'document_visits'
    id = mapped_column(String, primary_key=True, default=uid)
    user_id = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    document_id = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    day = mapped_column(String(10), nullable=False, index=True)
    count = mapped_column(Integer, default=1, nullable=False)
    last_visited = mapped_column(String, default=now, nullable=False)
    __table_args__ = (UniqueConstraint('user_id', 'document_id', 'day', name='uq_document_visit_day'),)
