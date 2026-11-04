"""Local Office conversion using an isolated, disposable LibreOffice profile."""
import os, shutil, subprocess, tempfile
from pathlib import Path
from threading import BoundedSemaphore

_GATE = BoundedSemaphore(1)
_FORMATS = {'doc','docx','ppt','pptx','xls','xlsx','odt','odp','ods','rtf'}
_TARGETS = {'pdf','doc','docx','ppt','pptx','xls','xlsx','odt','odp','ods'}

def executable():
    configured=os.getenv('LIBREOFFICE_CMD','')
    choices=[configured,shutil.which('soffice') or '',str(Path(__file__).resolve().parents[3]/'work/office-runtime/LibreOffice/program/soffice.com')]
    for value in choices:
        if value and Path(value).is_file():return str(Path(value).resolve())
    raise ValueError('Office preview/conversion is unavailable. Configure LIBREOFFICE_CMD. Your uploaded original is preserved and can be downloaded.')


def convert_office(data:bytes, extension:str, target:str='pdf')->bytes:
    if extension not in _FORMATS or target not in _TARGETS or extension==target:
        raise ValueError('Unsupported Office conversion.')
    command=executable()
    root=Path(os.getenv('TEMP',tempfile.gettempdir()))/'memoryvault-office'
    root.mkdir(parents=True,exist_ok=True)
    if not _GATE.acquire(timeout=5):raise ValueError('Another Office preview is being prepared. Please retry shortly.')
    try:
        with tempfile.TemporaryDirectory(prefix='convert-',dir=root) as directory:
            folder=Path(directory);profile=folder/'profile';(profile/'user').mkdir(parents=True)
            # A new profile has no trusted macro directories. Disable document
            # link updates and route Office's HTTP/HTTPS requests to a closed
            # loopback port; no hosted document viewer is used.
            settings='''<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Writer/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetProxyType" oor:op="fuse"><value>1</value></prop><prop oor:name="ooInetHTTPProxyName" oor:op="fuse"><value>127.0.0.1</value></prop><prop oor:name="ooInetHTTPProxyPort" oor:op="fuse"><value>9</value></prop><prop oor:name="ooInetHTTPSProxyName" oor:op="fuse"><value>127.0.0.1</value></prop><prop oor:name="ooInetHTTPSProxyPort" oor:op="fuse"><value>9</value></prop><prop oor:name="ooInetNoProxy" oor:op="fuse"><value></value></prop></item>
</oor:items>'''
            (profile/'user/registrymodifications.xcu').write_text(settings,encoding='utf-8')
            source=folder/('source.'+extension);source.write_bytes(data)
            out=folder/'out';out.mkdir()
            args=[command,'-env:UserInstallation='+profile.as_uri(),'--headless','--nologo','--nodefault','--norestore','--convert-to',target,'--outdir',str(out),str(source)]
            proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                stdout,stderr=proc.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
                else:proc.kill()
                proc.communicate()
                raise ValueError('Office conversion timed out. The original file remains available.') from None
            result=out/('source.'+target)
            if proc.returncode or not result.is_file():
                raise ValueError('This Office file could not be converted. It may be encrypted or damaged; the original remains available.')
            if result.stat().st_size>150*1024*1024:raise ValueError('Converted preview exceeds 150 MB. Download the original to view it.')
            converted=result.read_bytes()
            if target=='pdf' and not converted.startswith(b'%PDF-'):raise ValueError('Office conversion returned an invalid PDF.')
            return converted
    finally:
        _GATE.release()
