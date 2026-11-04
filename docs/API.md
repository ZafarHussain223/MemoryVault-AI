# API overview

Base URL: `/api/v1` through the Next.js same-origin proxy. Authenticated mutations require the session cookie plus `X-CSRF-Token` from `GET /auth/me`. Errors use FastAPI's `detail` field. All object IDs are owner-checked.

## Identity

- POST `/auth/register`, `/auth/login`, `/auth/logout`
- GET `/auth/me`, `/auth/sessions`
- DELETE `/auth/sessions/{id}`; POST `/auth/sessions/revoke-others`
- POST `/auth/forgot-password`, `/auth/reset-password`, `/auth/send-verification`, `/auth/verify`, `/auth/change-password`
- GET/PUT `/settings`; DELETE `/history`; DELETE `/account`

Recovery responses are generic. Password changes/reset revoke sessions. Local mail delivery is a private outbox when SMTP is not configured.

## Knowledge

- GET `/documents`: q, kind, tag, collection_id, sort, offset, limit (up to 100)
- GET/PATCH/DELETE `/documents/{id}`; GET `/{id}/download`; POST `/{id}/retry`
- POST `/notes`: title, content, tags; edits include the current version for conflict detection
- POST `/uploads`: multipart file, maximum 100 MiB by default; see [supported formats and limits](DOCUMENT_SUPPORT.md)
- GET `/documents/{id}/original`: authenticated original, with byte-range requests and safe inline MIME types
- GET `/documents/{id}/preview`: authenticated local Office-to-PDF rendering, or the original for other previewable types
- GET `/documents/{id}/text`: `offset` (default 0) and `limit` (1,000–50,000, default 20,000) characters; returns `text`, `offset`, `next_offset`, `total_characters`, `complete`
- POST `/imports`: `{url, kind: webpage|github|youtube, transcript?}`; returns a document. GitHub saves the public README; YouTube requires the supplied transcript.
- GET `/search`: q, document_id, kind, format, tag, collection_id, date_from, date_to. Dates use YYYY-MM-DD and mean saved date. Filters run before ranking.
- GET/POST `/collections`; PATCH/DELETE `/collections/{id}`; PUT/DELETE `/collections/{id}/items/{document_id}`

## Conversations

- GET `/conversations`; GET/PATCH/DELETE `/conversations/{id}`
- POST `/chat`: question, conversation_id?, document_id?
- POST `/chat/stream`: same body; SSE events sources, token, done or error. Only successfully completed answers are committed. Client disconnect cancels streaming.
- POST `/conversations/{id}/regenerate`: regenerate the last assistant answer against the current source context

Sources contain real chunk/document IDs, document_version, title, excerpt text, kind, format, saved date and page when available. Unconfigured generation returns an explicitly labeled retrieval-only response.

## AI knowledge and study

- GET/POST `/documents/{id}/insights`; POST `/documents/{id}/insights/apply-tags`
- GET `/study`; POST `/study/{document_id}`; PUT `/study/{study_id}/progress`
- GET `/quizzes`; POST `/quizzes/{document_id}`; GET/POST `/quizzes/{quiz_id}/attempts`
- GET/POST `/contradictions`; PATCH `/contradictions/{id}`

Generated output is schema-validated. Insights disclose covered passages. Quizzes withhold correct answers until submission. Stale source versions prevent applying outdated suggestions or recording new study progress. Comparisons return tentative, reviewable conflicts with exact source quotes.

## Graph, activity and portability

- GET `/graph`, `/dashboard`, `/recall`, `/notifications`
- POST `/recall/{document_id}/dismiss`, `/notifications/read`
- GET/POST `/relationships`; DELETE `/relationships/{id}`. Creation body: source_id, target_id, kind (related/references/prerequisite/part_of), note?. Relationships are explicitly user-created, unique and deleted with either source.
- GET `/export`: original JSON record export
- GET `/export/archive`: ZIP containing originals and all supported owned knowledge/study records

For exact validation limits and schemas, run the API and open its generated `/docs` OpenAPI interface. Production deployments may restrict or disable that interface.

## Profile photos, reminders and measured activity

- GET `/profile/photo/info`: presence, version and authenticated relative image URL.
- GET `/profile/photo`: private JPEG, no-store; PUT with multipart `file` to replace; DELETE to remove. Input limit: 2 MB, 8 million pixels, still JPEG/PNG/WebP. Output maximum: 512×512, metadata removed.
- GET/PUT `/notification-preferences`: `{processing, reminders, recall}` booleans.
- GET/POST `/reminders`: creation body `{title, document_id?: string|null, due_at: ISO8601-with-timezone}`. Time must be in the future and within 366 days. At most 500 per account.
- PATCH `/reminders/{id}`: title, linked source, due time and/or `status: pending|done`; DELETE to remove. Rescheduling resets delivery state; completing marks its notification read.
- PATCH `/notifications/{id}` with `{read: boolean}`; DELETE to remove. GET materializes due in-app reminders idempotently and at most one grounded recall notice per day. Deleting a notification does not cause immediate redelivery.
- POST `/documents/{id}/visit`: records an explicit open if history is enabled. Repeated opens within 30 seconds are coalesced. GET source details does not track visits.
- GET `/analytics?days=30|90`: owner-only UTC daily saves/searches/opens/quiz attempts, current vault/format/topic counts and persisted study totals. Other periods return 422.
- DELETE `/history` clears saved search and document-open history.

Reminders and recall notifications are checked on authenticated app requests; no background browser push or email scheduling is claimed. Notification preferences hide the corresponding processing event types without falsifying their underlying activity records.
