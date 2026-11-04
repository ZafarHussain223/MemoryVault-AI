import hashlib, io, json, re, secrets, time
from collections import Counter
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, Request, Response, BackgroundTasks, UploadFile, Query
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from . import ai_schemas
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, delete, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from .db import Reminder, DocumentVisit, Base, engine, DB, User, Session, Document, Chunk, Collection, Membership, Conversation, Message, Event, Study, Relationship, uid, now, get_db
from .security import current_user, owned, hash_token, rate_limit, password_hash, _dummy_hash
from .config import ORIGIN, SECURE, MAX_BYTES, QUOTA_BYTES
from .processing import validate, enqueue
from .ai import capabilities, retrieve, generate, generate_stream
from .search import exact_tag
from .quota import check_quota, lock_vault
from . import storage

@asynccontextmanager
async def lifespan(app):
    # Schema creation is owned by Alembic, never by request handlers.
    yield
app=FastAPI(title='MemoryVault API',version='0.1.0',lifespan=lifespan)
D=Annotated[DBSession,Depends(get_db)]
U=Annotated[User,Depends(current_user)]
prefix='/api/v1'
@app.middleware('http')
async def security_headers(request,call_next):
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        if origin and origin!=ORIGIN:
            return Response('Origin not allowed',status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store'
    return response
class Credentials(BaseModel):
    email:str=Field(max_length=254)
    password:str=Field(min_length=10,max_length=128)
    name:str=Field(default='',max_length=100)
    @field_validator('email')
    @classmethod
    def email_valid(cls,v):
        v=v.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):raise ValueError('Enter a valid email')
        return v
class NoteInput(BaseModel):
    title:str=Field(min_length=1,max_length=255)
    content:str=Field(default='',max_length=200000)
    tags:list[str]=Field(default_factory=list,max_length=30)
    version:int|None=None
    @field_validator('tags')
    @classmethod
    def clean_tags(cls,v):return list(dict.fromkeys(t.strip()[:50].lower() for t in v if t.strip()))
class CollectionInput(BaseModel):
    title:str=Field(min_length=1,max_length=100)
    rule_tag:str=Field(default='',max_length=50)
class ChatInput(BaseModel):
    question:str=Field(min_length=1,max_length=4000)
    conversation_id:str|None=None
    document_id:str|None=None
class Preferences(BaseModel):
    name:str=Field(max_length=100)
    history:bool=True
    recall:bool=True
    onboarded:bool=False
    use_case:str=Field(default='',max_length=100)
    interests:list[str]=Field(default_factory=list,max_length=20)
    theme:str='light'
    @field_validator('interests')
    @classmethod
    def clean_interests(cls, values):
        if any(len(value.strip()) > 50 for value in values):
            raise ValueError('Keep each interest within 50 characters.')
        return list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))
class ProgressInput(BaseModel):
    card:int=Field(ge=0,le=100)
    known:bool

def user_json(user):return {'id':user.id,'email':user.email,'name':user.name,'preferences':user.preferences}
def doc_json(doc,full=False):
    data={k:getattr(doc,k) for k in ['id','title','kind','format','tags','status','error','size','version','created','updated','source_url','source_type']}
    data['excerpt']=doc.content[:200]
    if full:data['content']=doc.content
    return data

def doc_detail(doc,db):
    data=doc_json(doc,True)
    data['content_characters']=len(doc.content or '')
    data['word_count']=len((doc.content or '').split())
    data['indexed_chunks']=db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id==doc.id))
    data['indexed_pages']=db.scalar(select(func.count(func.distinct(Chunk.page))).where(Chunk.document_id==doc.id))
    return data

def sign_in(db,user,response):
    token=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32)
    db.add(Session(token=hash_token(token),user_id=user.id,csrf=csrf,expires=int(time.time())+7*86400));db.commit()
    response.set_cookie('mv_session',token,httponly=True,secure=SECURE,samesite='lax',max_age=7*86400,path='/')
    return {'user':user_json(user),'csrf':csrf}
@app.get(prefix+'/health')
def health(db:D):
    db.execute(select(1))
    return {'ok':True}
@app.post(prefix+'/auth/register',status_code=201)
def register(body:Credentials,request:Request,response:Response,db:D):
    rate_limit('auth:'+request.client.host)
    user=User(email=body.email,password=password_hash.hash(body.password),name=body.name)
    db.add(user)
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'Unable to register this email. Try signing in.')
    return sign_in(db,user,response)
@app.post(prefix+'/auth/login')
def login(body:Credentials,request:Request,response:Response,db:D):
    rate_limit('auth:'+request.client.host)
    user=db.scalar(select(User).where(User.email==body.email))
    valid=password_hash.verify(body.password,user.password if user else _dummy_hash)
    if not user or not valid:raise HTTPException(401,'Email or password is incorrect.')
    return sign_in(db,user,response)
@app.get(prefix+'/auth/me')
def me(request:Request,user:U,db:D):
    session=db.get(Session,hash_token(request.cookies['mv_session']))
    return {'user':user_json(user),'csrf':session.csrf,'capabilities':capabilities()}
@app.post(prefix+'/auth/logout')
def logout(request:Request,response:Response,user:U,db:D):
    db.execute(delete(Session).where(Session.token==hash_token(request.cookies['mv_session'])));db.commit()
    response.delete_cookie('mv_session',path='/')
    return {'ok':True}
@app.get(prefix+'/documents')
def documents(user:U,db:D,q:str='',kind:str='',tag:str='',sort:str='newest',offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),collection_id:str=''):
    query=select(Document).where(Document.user_id==user.id)
    if q:query=query.where(Document.title.ilike('%'+q[:100].replace('%','').replace('_','')+'%'))
    if kind:query=query.where(Document.kind==kind)
    if collection_id:
        collection=owned(db,Collection,collection_id,user)
        if collection.rule_tag:tag=collection.rule_tag
        else:query=query.where(Document.id.in_(select(Membership.document_id).where(Membership.collection_id==collection_id)))
    if tag:query=query.where(exact_tag(db, tag.strip().lower()))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    query=query.order_by(Document.title if sort=='name' else Document.created.desc())
    return {'items':[doc_json(d) for d in db.scalars(query.offset(offset).limit(limit))],'total':total}
@app.get(prefix+'/documents/{document_id}')
def document(document_id:str,user:U,db:D):
    doc=owned(db,Document,document_id,user)
    return doc_detail(doc,db)
@app.post(prefix+'/notes',status_code=201)
def note(body:NoteInput,tasks:BackgroundTasks,user:U,db:D):
    check_quota(db, user.id, len(body.content.encode()))
    doc=Document(user_id=user.id,title=body.title,content=body.content,tags=body.tags,kind='note',size=len(body.content.encode()))
    db.add(doc);db.commit();enqueue(doc.id,tasks)
    return doc_json(doc,True)
@app.patch(prefix+'/documents/{document_id}')
def edit(document_id:str,body:NoteInput,tasks:BackgroundTasks,user:U,db:D):
    lock_vault(db, user.id)
    doc=owned(db,Document,document_id,user)
    if doc.status=='processing':raise HTTPException(409,'Wait for processing to finish before editing.')
    if body.version is not None and body.version!=doc.version:raise HTTPException(409,'This document changed in another tab. Reload before saving.')
    content_changed=doc.kind=='note' and doc.content!=body.content
    if content_changed:check_quota(db,user.id,len(body.content.encode())-doc.size)
    doc.title,doc.tags,doc.updated=body.title,body.tags,now()
    doc.version+=1
    if content_changed:
        doc.content,doc.status,doc.size=body.content,'pending',len(body.content.encode())
    db.commit()
    if content_changed:enqueue(doc.id,tasks)
    return doc_detail(doc,db)
@app.post(prefix+'/uploads',status_code=201)
async def upload(file:UploadFile,tasks:BackgroundTasks,user:U,db:D):
    rate_limit('upload:'+user.id,30)
    data=await file.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise HTTPException(413,f'Maximum file size is {MAX_BYTES // (1024*1024)} MB. The file was not uploaded.')
    title=(file.filename or 'untitled').replace('\\','/').split('/')[-1][:255]
    extension=title.rsplit('.',1)[-1].lower()
    try:validate(data,extension)
    except ImportError:raise HTTPException(503,'This parser is not installed. See server setup instructions.')
    except Exception as exc:raise HTTPException(422,str(exc)[:200] if isinstance(exc,ValueError) else 'Invalid file contents.')
    check_quota(db, user.id, len(data))
    digest=hashlib.sha256(data).hexdigest()
    duplicate=db.scalar(select(Document).where(Document.user_id==user.id,Document.digest==digest))
    if duplicate:raise HTTPException(409,'This file is already in your vault: '+duplicate.title)
    doc=Document(id=uid(),user_id=user.id,title=title,kind='file',format=extension,digest=digest,size=len(data))
    doc.key=user.id+'/'+doc.id
    try:storage.put(doc.key,data)
    except Exception:raise HTTPException(503,'Storage unavailable. The upload was not saved.')
    db.add(doc)
    try:db.commit()
    except Exception:db.rollback();storage.delete(doc.key);raise
    enqueue(doc.id,tasks)
    return doc_json(doc)
@app.post(prefix+'/documents/{document_id}/retry')
def retry(document_id:str,tasks:BackgroundTasks,user:U,db:D):
    doc=owned(db,Document,document_id,user)
    if doc.status not in {'failed','pending'}:raise HTTPException(409,'Only failed or pending documents can be retried.')
    doc.status='pending';doc.error='';db.commit();enqueue(doc.id,tasks)
    return {'ok':True}
@app.get(prefix+'/documents/{document_id}/download')
def download(document_id:str,request:Request,user:U,db:D):
    from .document_files import original_response
    return original_response(owned(db,Document,document_id,user),request,inline=False)
@app.delete(prefix+'/documents/{document_id}')
def remove_document(document_id:str,user:U,db:D):
    lock_vault(db, user.id)
    doc=owned(db,Document,document_id,user)
    if doc.status=='processing':raise HTTPException(409,'Wait for processing to finish before deleting.')
    storage.delete(doc.key)
    # Remove copied excerpts and generated study content as well as searchable chunks.
    for message in db.scalars(select(Message).join(Conversation).where(Conversation.user_id==user.id)):
        if any(c.get('document_id')==doc.id for c in message.citations):
            message.citations=[];message.content='This answer was removed because one of its sources was deleted.'
    db.execute(delete(Event).where(Event.user_id==user.id,Event.kind=='recall',Event.id.endswith(':'+doc.id)))
    reminder_ids=select(Reminder.id).where(Reminder.document_id==doc.id,Reminder.user_id==user.id)
    for reminder_id in db.scalars(reminder_ids):
        db.execute(delete(Event).where(Event.id=='reminder:'+reminder_id,Event.user_id==user.id))
    db.delete(doc);db.commit()
    return {'ok':True}
@app.get(prefix+'/search')
def search(q:str,user:U,db:D,document_id:str|None=None,kind:str='',format:str='',tag:str='',collection_id:str='',date_from:str='',date_to:str=''):
    if not q.strip() or len(q)>1000:raise HTTPException(422,'Enter a search of 1–1000 characters.')
    rate_limit('search:'+user.id,60)
    results=retrieve(db,user.id,q,document_id,filters={'kind':kind,'format':format,'tag':tag,'collection_id':collection_id,'date_from':date_from,'date_to':date_to})
    if user.preferences.get('history',True):db.add(Event(user_id=user.id,kind='search',text=q));db.commit()
    return {'items':results,'mode':capabilities()['search_mode']}
@app.get(prefix+'/collections')
def collections(user:U,db:D):
    result=[]
    for c in db.scalars(select(Collection).where(Collection.user_id==user.id).order_by(Collection.created.desc())):
        ids=[d.id for d in db.scalars(select(Document).where(Document.user_id==user.id)) if c.rule_tag in d.tags] if c.rule_tag else list(db.scalars(select(Membership.document_id).where(Membership.collection_id==c.id)))
        result.append({'id':c.id,'title':c.title,'rule_tag':c.rule_tag,'document_ids':ids,'count':len(ids)})
    return result
@app.post(prefix+'/collections',status_code=201)
def create_collection(body:CollectionInput,user:U,db:D):
    c=Collection(user_id=user.id,title=body.title,rule_tag=body.rule_tag.strip().lower());db.add(c);db.commit()
    return {'id':c.id,'title':c.title}
@app.patch(prefix+'/collections/{collection_id}')
def edit_collection(collection_id:str,body:CollectionInput,user:U,db:D):
    c=owned(db,Collection,collection_id,user);c.title=body.title;c.rule_tag=body.rule_tag.strip().lower();db.commit();return {'ok':True}
@app.delete(prefix+'/collections/{collection_id}')
def delete_collection(collection_id:str,user:U,db:D):
    db.delete(owned(db,Collection,collection_id,user));db.commit();return {'ok':True}
@app.put(prefix+'/collections/{collection_id}/items/{document_id}')
def add_member(collection_id:str,document_id:str,user:U,db:D):
    c=owned(db,Collection,collection_id,user);owned(db,Document,document_id,user)
    if c.rule_tag:raise HTTPException(409,'Smart collection membership is controlled by tags.')
    if not db.get(Membership,(collection_id,document_id)):db.add(Membership(collection_id=collection_id,document_id=document_id));db.commit()
    return {'ok':True}
@app.delete(prefix+'/collections/{collection_id}/items/{document_id}')
def remove_member(collection_id:str,document_id:str,user:U,db:D):
    owned(db,Collection,collection_id,user);owned(db,Document,document_id,user)
    db.execute(delete(Membership).where(Membership.collection_id==collection_id,Membership.document_id==document_id));db.commit();return {'ok':True}
@app.get(prefix+'/conversations')
def conversations(user:U,db:D):return [{'id':c.id,'title':c.title} for c in db.scalars(select(Conversation).where(Conversation.user_id==user.id).order_by(Conversation.created.desc()))]
@app.get(prefix+'/conversations/{conversation_id}')
def messages(conversation_id:str,user:U,db:D):
    owned(db,Conversation,conversation_id,user)
    return [{'id':m.id,'role':m.role,'content':m.content,'citations':m.citations} for m in db.scalars(select(Message).where(Message.conversation_id==conversation_id).order_by(Message.created))]
@app.delete(prefix+'/conversations/{conversation_id}')
def remove_conversation(conversation_id:str,user:U,db:D):
    db.delete(owned(db,Conversation,conversation_id,user));db.commit();return {'ok':True}
class RenameInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)


@app.patch(prefix+'/conversations/{conversation_id}')
def rename_conversation(conversation_id: str, body: RenameInput, user: U, db: D):
    title = body.title.strip()
    if not title:
        raise HTTPException(422, 'Enter a conversation title.')
    conversation = owned(db, Conversation, conversation_id, user)
    conversation.title = title
    db.commit()
    return {'id': conversation.id, 'title': conversation.title}


def prepare_chat(body, user, db, regenerate=False):
    rate_limit('ai:' + user.id, 15)
    conversation = owned(db, Conversation, body.conversation_id, user) if body.conversation_id else Conversation(id=uid(), user_id=user.id, title=body.question[:80], revision=1)
    history = list(db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created.desc()).limit(10)))[::-1] if body.conversation_id else []
    replacing = None
    if regenerate:
        if len(history) < 2 or history[-1].role != 'assistant' or history[-2].role != 'user':
            raise HTTPException(409, 'There is no completed answer to regenerate.')
        replacing, question = history[-1], history[-2].content
        history = history[:-2]
    else:
        question = body.question
    if not question.strip():
        raise HTTPException(422, 'Enter a question.')
    if body.document_id:
        owned(db, Document, body.document_id, user)
    previous = next((m.content for m in reversed(history) if m.role == 'user'), '')
    query = (previous[-1200:] + '\n' + question).strip() if previous else question
    sources = retrieve(db, user.id, query, body.document_id)
    context = '\n'.join(f'{m.role.upper()}: {m.content[:1200]}' for m in history[-6:])
    prompt = f'CONVERSATION CONTEXT (not source evidence):\n{context}\n\nCURRENT QUESTION:\n{question}' if context else question
    return {'conversation': conversation, 'revision': conversation.revision, 'new': not body.conversation_id,
            'question': question, 'prompt': prompt, 'sources': sources, 'replacing': replacing}


def check_answer_references(answer, sources):
    references = [int(n) for n in re.findall(r'\[(\d+)\]', answer)]
    if any(not 1 <= n <= len(sources) for n in references):
        raise HTTPException(502, 'The AI returned an invalid citation. Please regenerate the answer.')


def save_chat(db, user, prepared, answer):
    from .insights import check_versions
    check_answer_references(answer, prepared['sources'])
    check_versions(db, user, prepared['sources'])
    conversation = prepared['conversation']
    if prepared['new']:
        db.add(conversation)
        db.flush()
    else:
        changed = db.execute(update(Conversation).where(Conversation.id == conversation.id,
            Conversation.user_id == user.id, Conversation.revision == prepared['revision']).values(revision=Conversation.revision + 1).execution_options(synchronize_session=False))
        if not changed.rowcount:
            db.rollback()
            raise HTTPException(409, 'This conversation changed in another tab. Reload before trying again.')
    if prepared['replacing']:
        message = prepared['replacing']
        message.content, message.citations = answer, prepared['sources']
    else:
        db.add(Message(conversation_id=conversation.id, role='user', content=prepared['question']))
        message = Message(conversation_id=conversation.id, role='assistant', content=answer, citations=prepared['sources'])
        db.add(message)
    db.commit()
    return {'conversation_id': conversation.id, 'message': {'id': message.id, 'role': 'assistant', 'content': answer, 'citations': prepared['sources']}}


def retrieval_answer(sources):
    if not sources:
        return 'I could not find relevant information in your saved sources. Try another question or add a document.'
    return 'Retrieval-only mode: no generative AI provider is configured. These are the matching passages from your vault; no AI answer has been generated.'


@app.post(prefix+'/chat')
async def chat(body: ChatInput, request: Request, user: U, db: D):
    prepared = await run_in_threadpool(prepare_chat, body, user, db)
    sources = prepared['sources']
    answer = await generate(prepared['prompt'], sources) if sources and capabilities()['generation'] else retrieval_answer(sources)
    if await request.is_disconnected():
        raise HTTPException(499, 'The request was cancelled. No answer was saved.')
    return save_chat(db, user, prepared, answer)


@app.post(prefix+'/conversations/{conversation_id}/regenerate')
async def regenerate_chat(conversation_id: str, request: Request, user: U, db: D):
    prepared = await run_in_threadpool(prepare_chat, ChatInput(question='regenerate', conversation_id=conversation_id), user, db, regenerate=True)
    sources = prepared['sources']
    answer = await generate(prepared['prompt'], sources) if sources and capabilities()['generation'] else retrieval_answer(sources)
    if await request.is_disconnected():
        raise HTTPException(499, 'The request was cancelled. No answer was saved.')
    return save_chat(db, user, prepared, answer)


@app.post(prefix+'/chat/stream')
async def stream_chat(body: ChatInput, request: Request, user: U, db: D):
    prepared = await run_in_threadpool(prepare_chat, body, user, db)

    def event(kind, payload):
        return 'event: ' + kind + '\ndata: ' + json.dumps(payload) + '\n\n'

    async def events():
        saved = False
        try:
            yield event('sources', {'sources': prepared['sources']})
            if prepared['sources'] and capabilities()['generation']:
                pieces = []
                async for piece in generate_stream(prepared['prompt'], prepared['sources']):
                    if await request.is_disconnected():
                        return
                    pieces.append(piece)
                    yield event('token', {'text': piece})
                answer = ''.join(pieces)
            else:
                answer = retrieval_answer(prepared['sources'])
            if await request.is_disconnected():
                return
            result = save_chat(db, user, prepared, answer)
            saved = True
            yield event('done', result)
        except HTTPException as exc:
            yield event('error', {'message': exc.detail, 'status': exc.status_code})
        except Exception:
            yield event('error', {'message': 'The answer could not be completed. Please retry.', 'status': 500})
        finally:
            if not saved:
                db.rollback()
    return StreamingResponse(events(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'})

@app.get(prefix+'/dashboard')
def dashboard(user:U,db:D):
    docs=list(db.scalars(select(Document).where(Document.user_id==user.id).order_by(Document.created.desc())))
    counts=Counter(d.created[:10] for d in docs)
    events=list(db.scalars(select(Event).where(Event.user_id==user.id,Event.kind!='search').order_by(Event.created.desc()).limit(8)))
    return {'documents':sum(d.kind=='file' for d in docs),'notes':sum(d.kind=='note' for d in docs),'storage':sum(d.size for d in docs),'collections':db.scalar(select(func.count()).select_from(Collection).where(Collection.user_id==user.id)),'recent':[doc_json(d) for d in docs[:6]],'activity':[{'date':k,'count':v} for k,v in sorted(counts.items())],'events':[{'id':e.id,'text':e.text,'created':e.created} for e in events],'capabilities':capabilities()}
@app.get(prefix+'/graph')
def graph(user:U,db:D):
    docs=list(db.scalars(select(Document).where(Document.user_id==user.id).order_by(Document.created.desc()).limit(150)))
    nodes=[{'id':d.id,'title':d.title,'kind':d.kind,'tags':d.tags} for d in docs]
    edges=[]
    for i,a in enumerate(docs):
        for b in docs[i+1:]:
            shared=sorted(set(a.tags)&set(b.tags))
            if shared:edges.append({'id':a.id+':'+b.id,'source':a.id,'target':b.id,'label':'Shared tags: '+', '.join(shared),'type':'shared_tags','manual':False})
    from .relationships import RELATION_LABELS
    node_ids={doc.id for doc in docs}
    for relation in db.scalars(select(Relationship).where(Relationship.user_id==user.id,Relationship.source_id.in_(node_ids),Relationship.target_id.in_(node_ids))):
        edges.append({'id':relation.id,'source':relation.source_id,'target':relation.target_id,'label':RELATION_LABELS.get(relation.kind,relation.kind),'type':relation.kind,'manual':True,'note':relation.note})
    return {'nodes':nodes,'edges':edges,'basis':'Shared-tag connections are computed from your tags. Other relationships are explicitly created by you. The graph shows your 150 most recent memories.'}
@app.post(prefix+'/recall/{document_id}/dismiss')
def dismiss(document_id:str,user:U,db:D):
    lock_vault(db,user.id)
    db.refresh(user)
    owned(db,Document,document_id,user)
    user.preferences={**user.preferences,'dismissed':list(set(user.preferences.get('dismissed',[])+[document_id]))};db.commit();return {'ok':True}
@app.post(prefix+'/notifications/read')
def read_notifications(user:U,db:D):
    for e in db.scalars(select(Event).where(Event.user_id==user.id)):e.read=1
    db.commit();return {'ok':True}
@app.get(prefix+'/settings')
def settings(user:U):return {'user':user_json(user),'capabilities':capabilities()}
@app.put(prefix+'/settings')
def save_settings(body:Preferences,user:U,db:D):
    lock_vault(db,user.id)
    db.refresh(user)
    user.name=body.name;user.preferences={**user.preferences,**body.model_dump(exclude={'name'})};db.commit();return user_json(user)
@app.delete(prefix+'/history')
def clear_history(user:U,db:D):
    db.execute(delete(Event).where(Event.user_id==user.id,Event.kind=='search'))
    db.execute(delete(DocumentVisit).where(DocumentVisit.user_id==user.id))
    db.commit();return {'ok':True}
@app.get(prefix+'/export')
def export(user:U,db:D):
    data={'profile':user_json(user),'documents':[doc_json(d,True) for d in db.scalars(select(Document).where(Document.user_id==user.id))],'collections':collections(user,db),'conversations':[{'id':c.id,'title':c.title,'messages':messages(c.id,user,db)} for c in db.scalars(select(Conversation).where(Conversation.user_id==user.id))]}
    return Response(json.dumps(data),media_type='application/json',headers={'Content-Disposition':'attachment; filename=memoryvault-export.json'})
@app.delete(prefix+'/account')
def delete_account(user:U,db:D,response:Response):
    lock_vault(db, user.id)
    docs=list(db.scalars(select(Document).where(Document.user_id==user.id)))
    if any(d.status=='processing' for d in docs):raise HTTPException(409,'Wait for active processing to finish.')
    for d in docs:storage.delete(d.key)
    db.delete(user);db.commit();response.delete_cookie('mv_session',path='/');return {'ok':True}
def study_json(db, study):
    doc = db.get(Document, study.document_id)
    stale = not doc or doc.status != 'ready' or any(
        card.get('citation', {}).get('document_version') != doc.version for card in study.cards)
    return {'id': study.id, 'document_id': study.document_id, 'cards': study.cards,
            'progress': study.progress, 'stale': stale}


@app.get(prefix+'/study')
def studies(user: U, db: D):
    return [study_json(db, study) for study in db.scalars(select(Study).where(Study.user_id == user.id).order_by(Study.created.desc()))]


@app.post(prefix+'/study/{document_id}')
async def make_study(document_id: str, user: U, db: D):
    from .insights import source_chunks, check_versions, parse_json, valid_reference
    doc = owned(db, Document, document_id, user)
    rate_limit('ai:'+user.id, 15)
    sources = source_chunks(db, doc)
    answer = await generate('Create five useful flashcards.', sources,
        'Return only a JSON array of objects with question, answer and source (integer source number). '
        'Every answer must be supported by its cited excerpt. Do not invent facts. Keep each card concise.',
        response_format=ai_schemas.flashcards(len(sources)))
    try:
        cards = parse_json(answer)
        if not isinstance(cards, list) or not 1 <= len(cards) <= 20:
            raise ValueError()
        prepared = []
        for card in cards:
            if not isinstance(card, dict) or any(not isinstance(card.get(key), str) or not card[key].strip() or len(card[key]) > 2000 for key in ['question', 'answer']):
                raise ValueError()
            prepared.append({'question': card['question'], 'answer': card['answer'],
                'citation': valid_reference(card.get('source'), sources)})
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(502, 'The model returned invalid study content. Please retry.')
    check_versions(db, user, sources)
    study = Study(user_id=user.id, document_id=doc.id, cards=prepared)
    db.add(study)
    db.commit()
    return study_json(db, study)


@app.put(prefix+'/study/{study_id}/progress')
def study_progress(study_id:str,body:ProgressInput,user:U,db:D):
    s=owned(db,Study,study_id,user)
    if study_json(db, s)['stale']:raise HTTPException(409,'The source changed. Generate fresh flashcards before saving progress.')
    if body.card>=len(s.cards):raise HTTPException(422,'Invalid card')
    s.progress={**s.progress,str(body.card):body.known};db.commit();return {'ok':True}

from .accounts import router as account_router
app.include_router(account_router)

from .insights import router as insights_router
from .imports import router as imports_router
from .export_archive import router as export_archive_router
app.include_router(insights_router)
app.include_router(imports_router)
app.include_router(export_archive_router)

from .relationships import router as relationships_router
app.include_router(relationships_router)

from .engagement import router as engagement_router
app.include_router(engagement_router)

from .profile import router as profile_router
app.include_router(profile_router)

from .document_files import router as document_files_router
app.include_router(document_files_router)
