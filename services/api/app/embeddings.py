"""Small, bounded local embedding adapters sharing the existing vector schema."""
from functools import lru_cache
import math
import os
from urllib.parse import urlsplit

import httpx
from .config import EMBEDDINGS, EMBED_MODEL, EMBED_DIMENSIONS

ENABLED_BACKENDS = {'sentence-transformers', 'ollama'}
QUERY_INSTRUCTION = 'Given a question, retrieve relevant passages from saved documents that answer the question'
QUERY_VERSION = 'saved-passages-v1'
ERROR = 'Local embeddings are unavailable or invalid. Check the model service and configuration, then retry.'


def enabled():
    return EMBEDDINGS in ENABLED_BACKENDS


def model_identity():
    # Preserve compatibility with existing normalized MiniLM vectors. Ollama's
    # identity includes the dimensionality and query contract, preventing mixed
    # similarity calculations after a model or retrieval-contract change.
    if EMBEDDINGS == 'sentence-transformers':
        return EMBED_MODEL
    if EMBEDDINGS == 'ollama':
        revision = os.getenv('EMBEDDING_MODEL_REVISION', '').strip()
        return f'ollama:{EMBED_MODEL}:{revision or "tag"}:d{EMBED_DIMENSIONS}:{QUERY_VERSION}'
    return ''


def _number(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError()
        return value
    except ValueError:
        raise ValueError(f'Invalid {name}; use an integer from {minimum} to {maximum}.') from None


def _settings():
    if _number('EMBEDDING_DIMENSIONS', EMBED_DIMENSIONS, 32, 4096) != EMBED_DIMENSIONS:
        raise ValueError('This database requires 384-dimensional embeddings. A dimension change needs a migration and reindex.')
    endpoint = os.getenv('EMBEDDING_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
    parsed = urlsplit(endpoint)
    if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1', 'host.docker.internal'}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}):
        raise ValueError('Configure EMBEDDING_BASE_URL as the local Ollama HTTP origin.')
    return endpoint, _number('EMBEDDING_BATCH_SIZE', 8, 1, 16), _number('EMBEDDING_TIMEOUT_SECONDS', 120, 10, 300)


def _normalize(raw):
    if not isinstance(raw, (list, tuple)) or len(raw) != EMBED_DIMENSIONS:
        raise ValueError(ERROR)
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in raw):
        raise ValueError(ERROR)
    values = [float(value) for value in raw]
    length = math.hypot(*values)
    if not math.isfinite(length) or length <= 0:
        raise ValueError(ERROR)
    return [value / length for value in values]


@lru_cache(maxsize=1)
def embedding_model():
    """Lazy legacy adapter; Ollama never imports the native Python ML stack."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)


def embed(texts, *, query=False):
    if not isinstance(texts, (list, tuple)) or len(texts) > 2000:
        raise ValueError('Embed at most 2000 text passages at a time.')
    if not texts:
        return []
    if EMBEDDINGS == 'disabled':
        return [None] * len(texts)
    if not enabled():
        raise ValueError('Unsupported embedding backend. Use disabled, sentence-transformers or ollama.')
    if any(not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 24000 for text in texts):
        raise ValueError('Embedding inputs must be nonempty text passages of at most 24000 UTF-8 bytes.')
    if EMBEDDINGS == 'sentence-transformers':
        # Normalize and validate even if a replacement legacy adapter does not.
        try:
            raw = embedding_model().encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=False).tolist()
            if len(raw) != len(texts):
                raise ValueError(ERROR)
            return [_normalize(vector) for vector in raw]
        except Exception:
            raise ValueError(ERROR) from None
    endpoint, batch_size, timeout = _settings()
    result = []
    try:
        # Proxies and redirects must not send private document text elsewhere.
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=5), follow_redirects=False, trust_env=False) as client:
            revision = os.getenv('EMBEDDING_MODEL_REVISION', '').removeprefix('sha256:').strip()
            if revision:
                response = client.get(endpoint + '/api/tags')
                response.raise_for_status()
                installed = response.json().get('models', [])
                match = next((row for row in installed if row.get('model', row.get('name')) == EMBED_MODEL), None)
                if not match or match.get('digest', '').removeprefix('sha256:') != revision:
                    raise ValueError(ERROR)
            for offset in range(0, len(texts), batch_size):
                batch = list(texts[offset:offset + batch_size])
                if query:
                    batch = [f'Instruct: {QUERY_INSTRUCTION}\nQuery:{text}' for text in batch]
                response = client.post(endpoint + '/api/embed', json={
                    'model': EMBED_MODEL, 'input': batch, 'dimensions': EMBED_DIMENSIONS,
                    'truncate': False, 'keep_alive': _number('EMBEDDING_KEEP_ALIVE_SECONDS', 0, 0, 600),
                    'options': {'num_ctx': 4096, 'num_batch': 128},
                })
                response.raise_for_status()
                raw = response.json().get('embeddings')
                if not isinstance(raw, list) or len(raw) != len(batch):
                    raise ValueError(ERROR)
                result.extend(_normalize(vector) for vector in raw)
        return result
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError(ERROR) from None


def preflight():
    if not enabled():
        raise ValueError('Configure a supported embedding backend before reindexing.')
    # Actual inference catches missing models/dimension mismatches before any
    # ready document is marked pending. No downloaded weights are assumed ready.
    vector = embed(['Local embedding readiness check.'])[0]
    if vector is None:
        raise ValueError(ERROR)
    return model_identity()
