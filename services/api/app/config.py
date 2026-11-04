import os
from pathlib import Path
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/memoryvault.db")
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
ORIGIN = os.getenv("APP_ORIGIN", "http://localhost:3000")
SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
STORAGE = os.getenv("STORAGE_BACKEND", "local")
REDIS_URL = os.getenv("REDIS_URL", "")
EMBEDDINGS = os.getenv("EMBEDDING_BACKEND", "disabled")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b" if EMBEDDINGS == "ollama" else "sentence-transformers/all-MiniLM-L6-v2")
# The existing PostgreSQL vector column and index are 384-dimensional. Changing
# dimensions requires an explicit database migration and reindex, not an env edit.
EMBED_DIMENSIONS = 384
# Limits fail explicitly; originals are never silently shortened.
MAX_BYTES = int(os.getenv('MAX_UPLOAD_MB', '100')) * 1024 * 1024
MAX_DOCUMENT_PAGES = int(os.getenv('MAX_DOCUMENT_PAGES', '3000'))
MAX_EXTRACTED_CHARS = int(os.getenv('MAX_EXTRACTED_CHARS', '20000000'))
MAX_DOCUMENT_CHUNKS = int(os.getenv('MAX_DOCUMENT_CHUNKS', '25000'))
MAX_OCR_PAGES = int(os.getenv('MAX_OCR_PAGES', '1000'))
QUOTA_BYTES = 500 * 1024 * 1024
