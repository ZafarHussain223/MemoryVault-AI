# Architecture

The browser uses Next.js App Router. `/api/v1/*` is reverse-proxied to FastAPI, preserving same-origin cookies. Server-side authentication determines user ownership; browser-supplied user IDs are never accepted.

FastAPI uses SQLAlchemy and Alembic. Documents and notes share one owner-scoped model so ingestion, search, tags, collections and deletion follow the same paths. Extracted chunks retain source IDs, ordinal and real page numbers where available. Chats store source excerpts for traceability; deleting a source removes copied answer/source data that references it.

Production-oriented configuration uses PostgreSQL, a fixed 384-dimensional pgvector index, Redis/RQ for ingestion, and private S3 storage. Local mode deliberately uses SQLite, files beneath data/objects and FastAPI background tasks. SQLite/in-process mode is for development and small personal libraries, not a scalable service.

The client uses strict TypeScript, Radix dialogs for focus management, Lucide icons and React Markdown without raw HTML. Central CSS variables hold paper/ink/orange design tokens. A bounded SVG graph is used instead of React Flow to keep this initial implementation small; it derives shared-tag edges and displays persistent owner-created relationships, including their type and evidence notes. Accessible DOM charts display real server-derived aggregates without adding a charting runtime. Query/forms/state currently use typed fetch and React hooks instead of adding all preferred libraries before their features are needed.

Dependencies follow the Node lockfile. Python core ranges are in requirements-core.txt; optional backend libraries are in requirements.txt. No secrets or test accounts are seeded in the real user database.

## Processing ownership and verification

Each ingestion attempt claims the document with a timestamp and captures its source version. Completion and failure updates must still match that claim. Replacing chunks and publishing ready status happen in one transaction. An old worker finishing after operator recovery cannot overwrite the successful retry or its chunks. This protects retry correctness; automatic durable recovery scheduling still needs infrastructure acceptance.

Pytest runs create unique SQLite databases and private storage under work/tmp. Test configuration explicitly disables live Redis, S3, SMTP and LLM use. Browser checks similarly use separate data and real application servers. These test environments do not contain or reset the user's vault.

## Personal activity

The engagement module aggregates saved documents, explicitly recorded opens, searches and study attempts. Daily charts use UTC buckets; user reminder inputs use the device timezone and are normalized to UTC. In-app notification polling materializes due reminders and bounded recall notices from saved source evidence. It does not promise background push/email. User preferences control recording and notification visibility.

The profile module stores one bounded, metadata-free JPEG blob with the user. That choice keeps replacement and deletion transactional without adding a separate public upload directory.
