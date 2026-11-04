import os,secrets,time,smtplib
from email.message import EmailMessage
from fastapi import APIRouter,Depends,HTTPException,Request,Response,BackgroundTasks
from pydantic import BaseModel,Field
from sqlalchemy import select,delete,update
from sqlalchemy.orm import Session as DBSession
from .db import AuthToken,User,Session,get_db
from .security import hash_token,password_hash,rate_limit,current_user
from .config import DATA_DIR,ORIGIN
router=APIRouter(prefix='/api/v1/auth',tags=['account-recovery'])
class EmailInput(BaseModel):
    email:str=Field(min_length=3,max_length=254)
class TokenInput(BaseModel):
    token:str=Field(min_length=20,max_length=200)
class ResetInput(TokenInput):
    password:str=Field(min_length=10,max_length=128)
class ChangeInput(BaseModel):
    current_password:str=Field(max_length=128)
    password:str=Field(min_length=10,max_length=128)
def deliver(email,token,kind):
    message=EmailMessage()
    message['From']=os.getenv('SMTP_FROM','memoryvault@localhost')
    message['To']=email
    message['Subject']='Verify your MemoryVault email' if kind=='verify' else 'Reset your MemoryVault password'
    route='verify' if kind=='verify' else 'reset-password'
    message.set_content(f'Open this link within 30 minutes:\n{ORIGIN}/{route}?token={token}\n\nIf you did not request this, ignore this message.')
    host=os.getenv('SMTP_HOST','')
    if not host:
        if os.getenv('MAIL_MODE','local')!='local':raise RuntimeError('SMTP is not configured')
        outbox=DATA_DIR/'outbox';outbox.mkdir(parents=True,exist_ok=True)
        (outbox/(secrets.token_hex(16)+'.eml')).write_text(message.as_string(),encoding='utf-8')
        return
    with smtplib.SMTP(host,int(os.getenv('SMTP_PORT','587')),timeout=15) as smtp:
        smtp.starttls()
        if os.getenv('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
        smtp.send_message(message)
def issue(db,user,kind,tasks):
    raw=secrets.token_urlsafe(48)
    db.execute(delete(AuthToken).where(AuthToken.user_id==user.id,AuthToken.kind==kind))
    db.add(AuthToken(token=hash_token(raw),user_id=user.id,kind=kind,expires=int(time.time())+1800));db.commit()
    tasks.add_task(deliver,user.email,raw,kind)
def consume(db,token,kind):
    hashed=hash_token(token)
    claimed=db.execute(update(AuthToken).where(AuthToken.token==hashed,AuthToken.kind==kind,AuthToken.used==0,AuthToken.expires>time.time()).values(used=1))
    if not claimed.rowcount:db.rollback();raise HTTPException(400,'This link is invalid or expired. Request a new one.')
    return db.get(User,db.get(AuthToken,hashed).user_id)
@router.post('/forgot-password')
def forgot(body:EmailInput,request:Request,tasks:BackgroundTasks,db:DBSession=Depends(get_db)):
    rate_limit('recovery:'+request.client.host,5)
    user=db.scalar(select(User).where(User.email==body.email.strip().lower()))
    if user:issue(db,user,'reset',tasks)
    return {'message':'If an account exists, password reset instructions have been sent. Local development mail is saved in the server outbox.'}
@router.post('/reset-password')
def reset(body:ResetInput,request:Request,db:DBSession=Depends(get_db)):
    rate_limit('reset:'+request.client.host,10)
    user=consume(db,body.token,'reset')
    user.password=password_hash.hash(body.password)
    db.execute(delete(Session).where(Session.user_id==user.id));db.execute(delete(AuthToken).where(AuthToken.user_id==user.id));db.commit()
    return {'message':'Password updated. Sign in again on each device.'}
@router.post('/send-verification')
def verification(tasks:BackgroundTasks,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    rate_limit('verify:'+user.id,3);issue(db,user,'verify',tasks)
    return {'message':'Verification instructions sent. In local development, open the email in data/outbox on the server.'}
@router.post('/verify')
def verify(body:TokenInput,request:Request,db:DBSession=Depends(get_db)):
    rate_limit('verify-token:'+request.client.host,10)
    user=consume(db,body.token,'verify');user.preferences={**user.preferences,'email_verified':True};db.commit()
    return {'message':'Your email has been verified.'}
@router.post('/change-password')
def change(body:ChangeInput,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    rate_limit('change-password:'+user.id,5)
    from .quota import lock_vault
    lock_vault(db, user.id)
    db.refresh(user)
    if not password_hash.verify(body.current_password,user.password):raise HTTPException(400,'Current password is incorrect.')
    user.password=password_hash.hash(body.password)
    db.execute(delete(Session).where(Session.user_id==user.id))
    db.execute(delete(AuthToken).where(AuthToken.user_id==user.id))
    db.commit()
    return {'message':'Password updated. Sign in again.'}


def session_id(session):
    # Public session identifiers are not bearer tokens or stored token hashes.
    return hash_token('session-display:' + session.token)


@router.get('/sessions')
def list_sessions(request: Request, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    current = hash_token(request.cookies.get('mv_session', ''))
    sessions = db.scalars(select(Session).where(Session.user_id == user.id, Session.expires > int(time.time())).order_by(Session.expires.desc()))
    return [{'id': session_id(s), 'expires': s.expires, 'current': s.token == current} for s in sessions]


@router.post('/sessions/revoke-others')
def revoke_others(request: Request, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    current = hash_token(request.cookies.get('mv_session', ''))
    db.execute(delete(Session).where(Session.user_id == user.id, Session.token != current))
    db.commit()
    return {'ok': True}


@router.delete('/sessions/{identifier}')
def revoke_session(identifier: str, request: Request, response: Response, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    session = next((s for s in db.scalars(select(Session).where(Session.user_id == user.id)) if secrets.compare_digest(session_id(s), identifier)), None)
    if not session:
        raise HTTPException(404, 'Session not found.')
    current = session.token == hash_token(request.cookies.get('mv_session', ''))
    db.delete(session)
    db.commit()
    if current:
        response.delete_cookie('mv_session', path='/')
    return {'ok': True, 'current': current}
