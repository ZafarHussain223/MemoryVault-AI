"""Authenticated original files, local Office previews, and complete text paging."""
import io,os
from pathlib import Path
from threading import Lock
from urllib.parse import quote
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.responses import FileResponse,Response,StreamingResponse
from sqlalchemy.orm import Session
from .db import Document,User,get_db
from .security import current_user,owned,rate_limit
from .config import DATA_DIR,STORAGE
from . import storage
from .office import convert_office

router=APIRouter(prefix='/api/v1',tags=['document-files'])
OFFICE={'doc','docx','ppt','pptx','xls','xlsx','odt','odp','ods','rtf'}
IMAGES={'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp'}
TEXT={'txt','md','csv','tsv','json','log','html','htm','xml','yaml','yml'}
_PREVIEW_LOCK=Lock()

def filename(doc):
    name=''.join(c for c in doc.title.replace('\\','/').split('/')[-1] if ord(c)>=32)
    if not name.lower().endswith('.'+doc.format):name+='.'+doc.format
    return name or 'document.'+doc.format


def headers():
    return {'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'SAMEORIGIN','Content-Security-Policy':"frame-ancestors 'self'"}


def bytes_response(data,request,media_type,name,inline=True):
    # S3 fallback and generated note originals support the same bounded single
    # byte ranges as local FileResponse, enabling PDF browser navigation.
    extra=headers();extra['Accept-Ranges']='bytes'
    extra['Content-Disposition']=("inline" if inline else "attachment")+"; filename*=UTF-8''"+quote(name)
    start,end=0,len(data)-1;status=200
    value=request.headers.get('range')
    if value:
        try:
            if not value.startswith('bytes=') or ',' in value:raise ValueError()
            a,b=value[6:].split('-',1)
            if a:
                start=int(a);end=min(int(b),end) if b else end
            else:
                suffix=int(b)
                if suffix<=0:raise ValueError()
                start=max(0,len(data)-suffix)
            if start<0 or start> end or start>=len(data):raise ValueError()
        except (ValueError,TypeError):
            return Response(status_code=416,headers={**extra,'Content-Range':f'bytes */{len(data)}'})
        extra['Content-Range']=f'bytes {start}-{end}/{len(data)}';status=206
    extra['Content-Length']=str(end-start+1)
    def blocks():
        for offset in range(start,end+1,65536):yield data[offset:min(end+1,offset+65536)]
    return StreamingResponse(blocks(),status_code=status,media_type=media_type,headers=extra)


def original_response(doc,request,inline=True):
    media='application/pdf' if doc.format=='pdf' else IMAGES.get(doc.format,'text/plain' if doc.format in TEXT or not doc.key else 'application/octet-stream')
    show=inline and media!='application/octet-stream'
    extra=headers()
    if media=='text/plain':extra['Content-Security-Policy']="default-src 'none'; frame-ancestors 'self'; sandbox"
    if doc.key and STORAGE=='local':
        path=storage.local_path(doc.key)
        if not path.is_file():raise HTTPException(404,'Original file is unavailable.')
        return FileResponse(path,filename=filename(doc),media_type=media,content_disposition_type='inline' if show else 'attachment',headers=extra)
    try:data=storage.get(doc.key) if doc.key else doc.content.encode('utf-8')
    except Exception:raise HTTPException(503,'Original storage is temporarily unavailable.') from None
    response=bytes_response(data,request,media,filename(doc),show)
    response.headers.update(extra)
    return response


@router.get('/documents/{document_id}/original')
def original(document_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return original_response(owned(db,Document,document_id,user),request)


@router.get('/documents/{document_id}/text')
def full_text(document_id:str,offset:int=Query(0,ge=0),limit:int=Query(20000,ge=1000,le=50000),user:User=Depends(current_user),db:Session=Depends(get_db)):
    doc=owned(db,Document,document_id,user)
    total=len(doc.content or '')
    if offset>total:raise HTTPException(416,'Text position is beyond this document.')
    end=min(total,offset+limit)
    return {'text':(doc.content or '')[offset:end],'offset':offset,'next_offset':end if end<total else None,'total_characters':total,'complete':end>=total}


@router.get('/documents/{document_id}/preview')
def preview(document_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    doc=owned(db,Document,document_id,user)
    if doc.format not in OFFICE:return original_response(doc,request)
    if not doc.key:raise HTTPException(422,'This memory has no original Office file.')
    # This private local cache is only accessible through an owner-checked route.
    path=storage.preview_path(doc.key)
    if not path.is_file():
        rate_limit('preview:'+user.id,20)
        if not _PREVIEW_LOCK.acquire(timeout=5):raise HTTPException(503,'Another preview is being prepared. Please retry shortly.')
        try:
            if not path.is_file():
                try:result=convert_office(storage.get(doc.key),doc.format,'pdf')
                except ValueError as exc:raise HTTPException(503,str(exc)) from None
                except Exception:raise HTTPException(503,'Preview could not be prepared. The original is still available.') from None
                path.parent.mkdir(parents=True,exist_ok=True)
                temporary=path.with_suffix('.pending')
                temporary.write_bytes(result);temporary.replace(path)
        finally:_PREVIEW_LOCK.release()
    return FileResponse(path,media_type='application/pdf',filename=Path(filename(doc)).stem+'.pdf',content_disposition_type='inline',headers=headers())
