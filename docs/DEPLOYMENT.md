# Deployment

Do not expose the current application publicly without completing the production items in SECURITY.md and FEATURES.md.

## Local native workflow

Run `dev.ps1 install` once if dependencies are missing, then `dev.ps1 api` and `dev.ps1 web` in separate PowerShell terminals. The launcher keeps dependency caches and temporary files under the checkout. Native core mode uses SQLite, private local objects and background tasks; no external AI key is required. Use http://localhost:3000 consistently.

## Docker workflow (not executed here)

Install Docker Desktop with Linux containers. Copy .env.example to .env, set local passwords and desired provider. Run `docker compose config` before `docker compose up --build`. Migration and private bucket setup run before API health becomes available. The worker reads the same database, model cache and object storage configuration as the API. First embedding use downloads model weights.

For a production environment, use managed or backed-up PostgreSQL/S3/Redis; a proper HTTPS ingress; exact APP_ORIGIN; COOKIE_SECURE=true; SMTP_HOST/PORT/USER/PASSWORD/FROM and MAIL_MODE=smtp; rotated secrets; network isolation; and monitored workers. Apply migrations once before serving traffic, and test restore procedures. The web Dockerfile uses full regular Next output instead of standalone tracing to avoid the observed Windows packaging limitation.

## Environment variables

- DATABASE_URL: SQLAlchemy SQLite or postgresql+psycopg URL.
- APP_ORIGIN: exact browser origin, default http://localhost:3000.
- COOKIE_SECURE: true behind HTTPS, false only for local HTTP.
- DATA_DIR: private local data directory, default ./data relative to API.
- STORAGE_BACKEND: local or s3; S3_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET configure private objects.
- REDIS_URL: enables RQ ingestion and Redis rate limiting.
- EMBEDDING_BACKEND: disabled or sentence-transformers; fixed 384-dimension model.
- HF_HOME: model cache; dev.ps1 places it under work/.
- LLM_PROVIDER/MODEL/API_KEY/BASE_URL: explicit generative provider configuration.
- SMTP_HOST/PORT/USER/PASSWORD/FROM: TLS SMTP configuration.
- MAIL_MODE: local by default (private outbox); use smtp in production.
- API_URL: frontend proxy target, default http://127.0.0.1:8000; Docker builds use http://api:8000.
- NEXT_SWC_PATH: compiler download/cache directory; launcher places it on E:.
- NEXT_DIST_DIR: optional Next build directory override.
- LIBREOFFICE_CMD: local headless Office executable for legacy DOC/PPT/XLS ingestion and Office-to-PDF previews. The local setup is documented in DOCUMENT_SUPPORT.md; container deployments must install/configure their own converter.
- MAX_UPLOAD_MB/MAX_DOCUMENT_PAGES/MAX_EXTRACTED_CHARS/MAX_DOCUMENT_CHUNKS/MAX_OCR_PAGES: explicit document limits; defaults and corresponding frontend proxy limits are documented in DOCUMENT_SUPPORT.md.

## Observed environment limitations


The browser test runner starts its API and Next.js servers in the same process environment and cleans them up afterward. Tools in different isolation contexts may not reach one another's localhost servers. The user-facing application should be started using the normal PowerShell commands. No firewall or Windows protection was disabled.

## Verified local build workflow

Windows builds use `.next-production`, Webpack/WASM and one static build worker to reduce concurrency after intermittent output-directory errors. The cause of every Windows EPERM error has not been established. Normal Linux builds retain default worker behavior. Run `npm run build`, then `npm start` from apps/web with the API running. TypeScript and the ordinary production build are checked; standalone packaging and the Compose stack still need an environment with Docker.

`./dev.ps1 e2e` runs isolated browser workflows with a separate database and Chrome. To check a completed default production build against the same isolated API, run `python scripts/run_browser_tests.py --production` with the core Python dependencies available. The runner owns its server subprocesses and tears them down after verification.

Do not enable public use solely because the local browser suite passes. PostgreSQL/pgvector, Redis worker behavior, private object storage, SMTP delivery, live providers, reverse-proxy limits, restore drills and load behavior remain deployment acceptance checks.
