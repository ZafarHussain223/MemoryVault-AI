# AI and ingestion pipeline

Upload validates size, extension and supported signatures/text, detects duplicate file bytes per user, stores a private original, persists metadata, then schedules ingestion. Worker claims processing with a conditional database update. It extracts content and creates overlapping 1,200-character chunks with 160-character overlap. PDF page numbers come from the parser; other formats have no invented pages.

Text PDF extraction uses pypdf, a lightweight substitute for PyMuPDF for the current text-only PDF path. DOCX includes paragraphs/tables. Text, Markdown, CSV and JSON use validated UTF-8. Images optionally use Pillow/Tesseract. Scanned PDF OCR remains future work. File failures retain the original and expose a retry action.

Optional local semantic embeddings use Sentence Transformers all-MiniLM-L6-v2 with 384 normalized dimensions. PostgreSQL retrieves by cosine distance, then combines semantic and lexical scores. Local SQLite performs bounded exact scoring over at most 5,000 chunks. Keyword-only mode uses token overlap and is clearly labeled. Current hybrid retrieval on PostgreSQL considers semantic candidates only; a separate lexical candidate union and richer filters remain outstanding.

Chat retrieves at most eight owner-scoped chunks, bounds the source context and sends it to the explicitly configured provider. It treats document content as data, supplies no tools, and attaches actual retrieved passages to the answer. These controls reduce prompt-injection risk but do not guarantee model factual accuracy. The model can still output incorrect inline citation numbers; returned source cards remain genuine. Citation claim validation and conversational follow-up context remain to implement.

With no provider, chat returns a clear retrieval-only message and source excerpts. It never substitutes invented answers. Provider failures return 502 without saving a fabricated response. Provider-backed flashcards validate structure and source indexes before persistence.

No live generation, model-weight download, OCR executable, PostgreSQL or Redis worker was verified in this environment. The deterministic API suite verifies the keyword pipeline, extraction, missing-provider and failure behavior.

## Generation and ingestion updates

Chat supports bounded conversational context, genuine SSE for configured OpenAI-compatible/Gemini/Ollama providers, cancellation and end-of-stream validation. Sources are snapshots of owner-scoped chunks with document versions. Answers are committed only after a complete response and a freshness check. Retrieval-only mode remains available without a provider.

Document insights persist structured summary/detail/concepts/takeaways/categories/entities with actual source references and coverage counts. Suggestions are not applied automatically. Flashcards, quizzes and comparison results validate schema, citations and source versions. Contradiction quotes must occur in supplied passages; results remain tentative for user review.

Public import reads validated article text or a public GitHub README through a DNS/IP-pinned bounded fetcher. YouTube uses an explicit pasted transcript. Imported material follows the same private storage/index pipeline and keeps a source URL and source type.

Search filters run before candidate ranking. Hybrid retrieval includes lexical candidates as well as vector candidates, so exact identifiers are retained. SQLite semantic scoring is limited to 5,000 recent indexed chunks; lexical candidate scoring is limited to 1,500 matches. PostgreSQL pgvector uses a bounded nearest-neighbor query. These are documented scaling limits, not a claim of exhaustive relevance at arbitrary library size.

`python -m app.maintenance reindex` loads the configured embedding model before replacing indexes. `recover` marks processing older than 20 minutes failed so the owner can retry. Stop/inspect workers before operator recovery. A production durable lease/cleanup system remains future work.
