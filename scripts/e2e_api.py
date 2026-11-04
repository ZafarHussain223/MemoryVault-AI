"""Start an isolated API database for browser tests. Never uses the user's vault."""
import os
from pathlib import Path
import tempfile
import sys
root = Path(__file__).resolve().parents[1]
run = Path(tempfile.mkdtemp(prefix='browser-', dir=root/'work' if (root/'work').exists() else None))
os.environ['DATABASE_URL'] = 'sqlite:///'+(run/'test.db').as_posix()
os.environ['DATA_DIR'] = str(run/'storage')
os.environ['EMBEDDING_BACKEND'] = 'disabled'
os.environ['LLM_PROVIDER'] = 'none'
os.environ['LLM_API_KEY'] = ''
os.environ['MAIL_MODE'] = 'local'
os.environ['SMTP_HOST'] = ''
os.environ['APP_ORIGIN'] = 'http://127.0.0.1:3100'
os.environ['COOKIE_SECURE'] = 'false'
os.environ['REDIS_URL'] = ''
os.environ['STORAGE_BACKEND'] = 'local'
service = root/'services'/'api'
os.chdir(service)
sys.path.insert(0,str(service))
from alembic.config import Config
from alembic import command
command.upgrade(Config(str(service/'alembic.ini')), 'head')
import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=int(os.getenv('MV_E2E_API_PORT','8100')), log_level='warning')
