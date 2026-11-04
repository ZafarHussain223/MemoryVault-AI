"""Keep every pytest run separate from real vaults and other test processes."""
import os
from pathlib import Path
import tempfile

_workspace = Path(__file__).resolve().parents[3]
_test_root = _workspace / 'work' / 'tmp'
_test_root.mkdir(parents=True, exist_ok=True)
_test_directory = Path(tempfile.mkdtemp(prefix='api-tests-', dir=_test_root))
# Override deployment configuration before app imports, including when dev.ps1
# has read a configured .env.local. Tests must never contact live infrastructure.
os.environ.update({
    'DATABASE_URL': 'sqlite:///' + (_test_directory / 'test.db').as_posix(),
    'DATA_DIR': str(_test_directory / 'storage'),
    'EMBEDDING_BACKEND': 'disabled',
    'EMBEDDING_MODEL_REVISION': '',
    'EMBEDDING_KEEP_ALIVE_SECONDS': '0',
    'LLM_CONTEXT_LENGTH': '4096',
    'LLM_KEEP_ALIVE_SECONDS': '60',
    'LLM_REQUEST_TIMEOUT_SECONDS': '120',
    'LLM_PROVIDER': 'none',
    'LLM_API_KEY': '',
    'REDIS_URL': '',
    'STORAGE_BACKEND': 'local',
    'MAIL_MODE': 'local',
    'SMTP_HOST': '',
    'APP_ORIGIN': 'http://localhost:3000',
    'COOKIE_SECURE': 'false',
})
