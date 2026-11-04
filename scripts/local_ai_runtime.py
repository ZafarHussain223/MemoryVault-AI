"""Project-local Ollama process used by real-model verification; no cloud calls."""
from contextlib import contextmanager
from pathlib import Path
import json,os,socket,subprocess,time,urllib.request
ROOT=Path(__file__).resolve().parents[1]
CHAT_MODEL='qwen3:4b-instruct-2507-q4_K_M'
EMBED_MODEL='qwen3-embedding:0.6b'
EXECUTABLE=ROOT/'work/ai-runtime/ollama-0.40.12/ollama.exe'
def environment(port=11434,loaded_models=2):
 env=os.environ.copy();env.update({'OLLAMA_HOST':f'127.0.0.1:{port}','OLLAMA_MODELS':str(ROOT/'work/models/ollama'),'OLLAMA_NO_CLOUD':'1','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':str(loaded_models),'OLLAMA_MAX_QUEUE':'4','OLLAMA_CONTEXT_LENGTH':'4096','OLLAMA_FLASH_ATTENTION':'1','OLLAMA_KV_CACHE_TYPE':'q8_0','OLLAMA_KEEP_ALIVE':'60s','CUDA_CACHE_PATH':str(ROOT/'work/tmp/cuda-cache'),'CUDA_CACHE_MAXSIZE':'1073741824','TEMP':str(ROOT/'work/tmp'),'TMP':str(ROOT/'work/tmp')})
 Path(env['CUDA_CACHE_PATH']).mkdir(parents=True,exist_ok=True)
 return env
class Service:
 def __init__(self,port):self.base=f'http://127.0.0.1:{port}'
 def api(self,path,data=None,timeout=240):
  req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout) as response:return json.load(response)
@contextmanager
def local_service(log_name='local-ai-verification.log',loaded_models=2):
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 service=Service(port);path=ROOT/'work/ai-reports'/log_name
 with path.open('w',encoding='utf-8') as log:
  process=subprocess.Popen([str(EXECUTABLE),'serve'],env=environment(port,loaded_models),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  try:
   for _ in range(60):
    if process.poll() is not None:raise RuntimeError(f'Ollama exited {process.returncode}; see {path}')
    try:service.api('/api/version',timeout=2);break
    except (OSError,TimeoutError):time.sleep(1)
   else:raise RuntimeError(f'Ollama startup timed out; see {path}')
   yield service
  finally:
   if process.poll() is None:
    for model in [CHAT_MODEL,EMBED_MODEL]:
     try:service.api('/api/generate',{'model':model,'keep_alive':0},timeout=15)
     except Exception:pass
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill()
