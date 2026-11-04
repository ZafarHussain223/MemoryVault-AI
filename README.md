# MemoryVault AI

MemoryVault is a personal knowledge app for saving files, notes and web articles, searching their contents, and asking questions with links to the source. It pairs a Next.js frontend with a FastAPI backend. The default local setup stores each user's vault in SQLite and a private file directory.

## Run it on Windows

Install Git, Node.js 22 with npm, and Python 3.12 or newer with pip. Open PowerShell in the cloned repository and run:

```powershell
.\dev.ps1 install
Copy-Item .env.local.example .env.local
```

Create the configuration file on your first setup only. If the checkout already has a configured `.env.local`, keep that file.

Start each service in its own terminal from the repository root.

| Terminal | Command |
| --- | --- |
| API | `.\dev.ps1 api` |
| Website | `.\dev.ps1 web` |

Open [MemoryVault](http://localhost:3000) and create an account. The API launcher applies database migrations. Both terminal commands keep running while the app is in use.

## What you can use

- Save notes, upload files, organize collections and search your own sources. The reader displays PDFs, images and text directly and provides original downloads.
- Navigate complete extracted text in sections. Local LibreOffice adds Office previews and legacy Office ingestion. See [supported formats and limits](docs/DOCUMENT_SUPPORT.md).
- Connect a language model for cited answers, document insights, flashcards and quizzes. Without a model, the app displays matching passages for search and retrieval.
- Explore relationships between memories, recall older sources, set reminders and export your own vault.

## Optional local AI

Install Ollama and run it on this computer. In a terminal connected to that running Ollama service, download the models:

```powershell
ollama pull qwen3:4b-instruct-2507-q4_K_M
ollama pull qwen3-embedding:0.6b
```

Set the following in `.env.local`, leave Ollama running, and restart the API:

```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M
LLM_BASE_URL=http://127.0.0.1:11434
LLM_CONTEXT_LENGTH=8192
EMBEDDING_BACKEND=ollama
EMBEDDING_MODEL=qwen3-embedding:0.6b
EMBEDDING_BASE_URL=http://127.0.0.1:11434
```

For an existing vault, back it up before running `.\dev.ps1 reindex` after changing the embedding configuration. The [model lockfile](local-ai-models.lock.json) records the reference digests. The project also supports a separately provisioned portable Windows runtime with models under `work/models/ollama`. On an installation that already uses that layout, continue starting AI with `.\dev.ps1 ai`.

For scanned PDFs or image text extraction, install Tesseract and the OCR packages in `services/api/requirements-local-ai.txt`. For Office previews install LibreOffice. The example configuration includes optional executable paths.

## Development and checks

```powershell
.\dev.ps1 test
.\dev.ps1 e2e
```

The first command runs the API tests, TypeScript and a production build. Browser workflows use disposable vaults and synthetic fixtures. The Windows browser suite uses Chrome and requires LibreOffice for the PowerPoint preview test. GitHub Actions sets up the Linux test environment on a push or pull request.

See [architecture](docs/ARCHITECTURE.md), [API endpoints](docs/API.md), [feature coverage](docs/FEATURES.md) and [deployment](docs/DEPLOYMENT.md). Private uploads, development credentials, runtime binaries and model weights stay outside version control.
