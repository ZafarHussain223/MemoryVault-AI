"""Run browser checks in one Windows process group with bounded server cleanup."""
import os
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
web = root/'apps'/'web'
node = shutil.which('node')
if not node:
    raise SystemExit('Node.js is required.')
production='--production' in sys.argv
arguments=[arg for arg in sys.argv[1:] if arg!='--production']
api_port=8000 if production else 8100
env = os.environ.copy()
env.update({'MV_E2E_EXTERNAL_SERVERS':'1','API_URL':f'http://127.0.0.1:{api_port}','NEXT_DIST_DIR':os.getenv('MV_E2E_DIST_DIR','.next-production') if production else '.next-e2e','MV_E2E_API_PORT':str(api_port),'NEXT_TELEMETRY_DISABLED':'1'})
(root/'work').mkdir(exist_ok=True)
processes=[]
handles=[]


def start(command, cwd, logfile):
    handle=(root/'work'/logfile).open('w',encoding='utf-8')
    handles.append(handle)
    options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    process=subprocess.Popen(command,cwd=cwd,env=env,stdout=handle,stderr=subprocess.STDOUT,**options)
    processes.append(process)
    return process


def ready(url, process, seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError('Test server exited; see work/e2e-*-server.log.')
        try:
            with urllib.request.urlopen(url,timeout=4) as response:
                if response.status==200:return
        except (OSError,TimeoutError):pass
        time.sleep(.4)
    raise RuntimeError('Test server timed out; see work/e2e-*-server.log.')

code=1
try:
    api=start([sys.executable,str(root/'scripts'/'e2e_api.py')],root,'e2e-api-server.log')
    server_command=[node,str(web/'node_modules'/'next'/'dist'/'bin'/'next'),*(['start'] if production else ['dev','--webpack']),'--hostname','127.0.0.1','--port','3100']
    server=start(server_command,web,'e2e-web-server.log')
    ready(f'http://127.0.0.1:{api_port}/api/v1/health',api)
    ready('http://127.0.0.1:3100',server)
    print('Isolated browser test servers are ready.',flush=True)
    result=subprocess.run([node,str(web/'node_modules'/'playwright'/'cli.js'),'test','--reporter=list',*arguments],cwd=web,env=env)
    code=result.returncode
finally:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
    for handle in handles:handle.close()
    (root/'work'/'last-browser-run.json').write_text(json.dumps({'finished_at':datetime.now(timezone.utc).isoformat(),'mode':'production' if production else 'development','exit_code':code,'arguments':arguments},indent=2),encoding='utf-8')
raise SystemExit(code)
