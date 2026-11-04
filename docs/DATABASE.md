# Database

Tables: users, sessions, auth_tokens, documents, chunks, collections, collection_items, conversations, messages, events, study_sessions.

UUID strings identify resources. Sessions and account-recovery tokens store hashes, never raw bearer tokens. Sessions expire after seven days; recovery tokens after thirty minutes and are consumed with a conditional update.

Every root private resource has a user foreign key and ownership index. Chunks, memberships, messages and study records use cascading foreign keys. SQLite foreign keys are enabled on every connection. User preferences and simple tags/progress/citations are JSON. The current schema intentionally consolidates notes/files and events/notifications rather than introducing empty tables for unfinished features.

PostgreSQL chunk embeddings use pgvector Vector(384), plus a cosine HNSW index. SQLite stores optional vectors as JSON for local exact comparison. Only the fixed all-MiniLM-L6-v2 model is accepted. Reindexing is required when enabling embeddings for previously keyword-only data.

Run from services/api: `python -m alembic upgrade head`. Revisions 0001 and 0002 establish the current schema and account tokens. The initial migration currently references model metadata; freeze that baseline before independently evolving models in a production migration sequence.

Each pytest process uses a unique temporary database and private storage under work/tmp; browser checks use separate temporary vaults. Test configuration forces local infrastructure and disables live SMTP/AI. Development data is ignored by Git and Docker build context.

## Continued knowledge features

Migration 0003 adds document source URLs/types, conversation revisions, document_insights, quizzes, quiz_attempts and contradictions. Migration 0004 adds explicit relationships with user ownership, two cascading document references and a unique edge constraint. Generated artifacts store document versions to detect stale source material. Credentials and private tokens remain outside exported records.

Migrations were applied to the existing local SQLite database after creating a backup. Initial migrations still use current ORM metadata with compatibility checks for later additions; a frozen historical baseline and full PostgreSQL migration round-trip review remain production tasks.

## Profile, reminders and visits

Migration 0005 adds reminders (owned, optional cascading source, UTC due time, pending/done and notified timestamp) and document_visits (owned source/day uniqueness, last visit and daily count). Explicit open actions record visits only while history is enabled; repeated requests within 30 seconds do not inflate the count. Clearing history removes search events and visit records. Notification preferences, daily recall notice throttle and bounded notice history are saved in user preferences.

Migration 0006 adds profile_images: one canonical JPEG blob per user, version and update time. The authenticated endpoint does not accept an owner override. Account deletion cascades the image. Binary photo data is exported as profile/photo.jpg, not serialized into JSON.
