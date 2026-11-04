import hashlib, secrets, time
from collections import defaultdict, deque
from threading import Lock
from fastapi import HTTPException, Request, Depends
from sqlalchemy.orm import Session as DBSession
from .db import Session, User, get_db
from .config import REDIS_URL
from pwdlib import PasswordHash
password_hash = PasswordHash.recommended()
_dummy_hash = password_hash.hash("not-a-real-user-password")
_buckets = defaultdict(deque)
_lock = Lock()
def rate_limit(key: str, limit: int = 15):
    if REDIS_URL:
        from redis import Redis
        r = Redis.from_url(REDIS_URL)
        bucket = "rate:" + hashlib.sha256(key.encode()).hexdigest() + ":" + str(int(time.time()) // 60)
        n = r.incr(bucket)
        if n == 1: r.expire(bucket, 65)
        if n > limit: raise HTTPException(429, "Too many attempts. Please wait a minute.")
        return
    with _lock:
        now = time.monotonic()
        if len(_buckets) > 10000:
            for k in list(_buckets):
                if not _buckets[k] or _buckets[k][-1] < now - 60: del _buckets[k]
        q = _buckets[key]
        while q and q[0] < now - 60: q.popleft()
        if len(q) >= limit: raise HTTPException(429, "Too many attempts. Please wait a minute.")
        q.append(now)
def hash_token(token): return hashlib.sha256(token.encode()).hexdigest()
def current_user(request: Request, db: DBSession = Depends(get_db)):
    token = request.cookies.get("mv_session", "")
    session = db.get(Session, hash_token(token)) if token else None
    if not session or session.expires < time.time(): raise HTTPException(401, "Please sign in to your vault.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
            raise HTTPException(403, "Security token expired. Refresh and try again.")
    return db.get(User, session.user_id)
def owned(db, model, object_id, user):
    obj = db.get(model, object_id)
    if not obj or obj.user_id != user.id: raise HTTPException(404, "Not found")
    return obj
