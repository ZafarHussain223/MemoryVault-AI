# Feature and verification status

The table describes the implemented application and its verification boundaries.

| Area | Implemented behavior | Verification / remaining scope |
|---|---|---|
| Landing/motion | Paper/ink/orange knowledge identity; connected-memory examples, contextual cursor, scroll fills, process tabs and motion preference | Desktop/mobile browser checks; reduced motion supported |
| Authentication | Register/login/logout, hashed expiring sessions, reset/verification, password change, session revocation | API tests; browser login flow; SMTP delivery and mandatory verification gate pending |
| Onboarding/profile | Saved use case/interests, skip, name/theme/privacy settings; private resized profile photos with replacement/removal | API validation/isolation/export/erasure and browser persistence; full staged onboarding remains |
| Notes | Markdown toolbar/preview, persistent edits, serialized autosave, version conflicts, dirty-close protection | API and browser create/search/edit/delete; richer editor actions possible |
| File ingestion | Private originals, signatures, size/quota/digest checks, upload progress/cancel, processing/retry | Real PDF and text workflows tested; S3/RQ stack unexecuted |
| Parsers/OCR | 27 extensions including modern/legacy Office, OpenDocument, EPUB, RTF and structured text; PDF/image OCR; bounded complete indexing | Real Office parsing/conversion and 330-page PDF tests; Word imported content and mixed scan/text regressions; [formats and limits](DOCUMENT_SUPPORT.md) |
| Original reader | Owner-checked original PDF/image/text view, local Office PDF rendering, original downloads and complete extracted-text sections | Browser PowerPoint/long-book checks, private byte ranges, cache deletion and mobile layout verified; EPUB uses original download |
| Search | Owner-scoped hybrid integration; exact tag, type, format, collection, date filters before ranking | Keyword/filter tests plus actual Ollama/Qwen semantic search verified; scalable full-text index remains |
| Chat | Saved context, source snapshots, real provider SSE, cancel/rename/regenerate, partial-stream rejection, source version guard | Retrieval browser tests plus real local cited QA, follow-ups, cross-document answers and SSE verified |
| Collections | Create/rename/delete, manual membership, editable exact-tag rules | API and browser flow; optimistic checkbox with rollback |
| Graph | Shared-tag evidence plus persisted explicit related/references/prerequisite/part-of links and notes; delete/cascade; zoom/pan/search | API tests and UI; inferred semantic/entity edges, larger graph layout and fuller filtering remain |
| Timeline | Saved-date grouping; search can filter saved-date ranges | Uses loaded page of library; full timeline pagination/NL date queries remain |
| Recall | Transparent tag/interest/explicit-link/unvisited signals; real visit history, explain/dismiss/disable; bounded daily notices | API and browser tests; semantic and collection-based signals remain |
| AI insights | Persisted summary/detail/concepts/takeaways/categories/entities with real source references, version/coverage disclosure, apply tags | Deterministic validation/isolation tests and actual local model insights verified |
| Study | Flashcards/progress, quizzes, persisted attempts, source citations and stale-source protection | Deterministic tests and live generation of five cards/five questions verified; persisted study totals included in analytics |
| Contradictions | Model-generated tentative disagreements with exact quoted evidence; review/dismiss and version checks | Deterministic tests and live quoted-conflict comparison verified; results remain tentative interpretations |
| Imports | Public article text, public GitHub README, pasted YouTube transcript, canonical source metadata, indexing | Mock-fetch API/security tests; arbitrary sites vary; no whole repository or automatic video transcript claim |
| Analytics/notifications | Real 30/90-day saves/searches/opens/study charts and tables; formats/topics; read/unread/delete; persisted preferences; scheduled/rescheduled/completed linked reminders | API and production browser tests; reminders materialize while open/on return; no email/device-push service |
| Export/erasure | ZIP originals + profile photo + owned knowledge/study/reminders/visits/events; JSON export retained; cascading deletion and answer redaction | API and browser export tests; transactional storage cleanup and mail retention still need production hardening |
| Infrastructure | Compose PG/pgvector/Redis/MinIO/API/worker/web, CI configuration, safe local launcher, reindex/recovery tools | Existing SQLite data backed up and upgraded through 0006; stale-worker writes guarded; Docker and hosted CI not executed |
| Release | Expanded working application with automated checks | Not full master-spec completion or production approval |

No fabricated AI output or fake statistics are used in the product. Test mocks and isolated test accounts are confined to automated test workflows.
