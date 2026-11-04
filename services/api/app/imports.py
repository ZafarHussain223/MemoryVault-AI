"""Bounded public-source ingestion. DNS is validated AND pinned for each request."""
import base64
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit, urljoin, quote, parse_qs
from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Document, User, get_db, uid
from .security import current_user, rate_limit
from .quota import check_quota
from .processing import enqueue
from . import storage

router = APIRouter(prefix='/api/v1')
MAX_SOURCE_BYTES = 2 * 1024 * 1024
TIMEOUT = 12


def public_target(url: str):
    """Reject non-public destinations before opening a socket, including every redirect."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
            raise ValueError()
        host = parts.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        if port != (443 if parts.scheme == 'https' else 80) or any(ord(c) < 33 for c in url):
            raise ValueError()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(item[4][0] for item in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global or (getattr(ipaddress.ip_address(ip), 'ipv4_mapped', None) is not None and not ipaddress.ip_address(ip).ipv4_mapped.is_global) for ip in ips):
            raise ValueError()
    except (ValueError, UnicodeError, OSError):
        raise HTTPException(422, 'Use a public HTTP or HTTPS URL. Local, private and nonstandard network destinations are not supported.')
    normalized = urlunsplit((parts.scheme, '['+host+']' if ':' in host else host, parts.path or '/', parts.query, ''))
    return normalized, parts.scheme, host, port, ips[0]


class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, ip):
        super().__init__(host, port=port, timeout=TIMEOUT)
        self.pinned_ip = ip

    def connect(self):
        self.sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)


class PinnedHTTPS(PinnedHTTP):
    def connect(self):
        super().connect()
        try:
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)
        except Exception:
            self.sock.close()
            raise


def fetch_public(url: str, accept: str = 'text/html,text/plain'):
    for _ in range(4):
        normalized, scheme, host, port, ip = public_target(url)
        parsed = urlsplit(normalized)
        path = quote(parsed.path, safe='/%:@!$&\'()*+,;=-._~') + ('?' + parsed.query if parsed.query else '')
        conn = (PinnedHTTPS if scheme == 'https' else PinnedHTTP)(host, port, ip)
        try:
            conn.request('GET', path, headers={'Host': parsed.netloc, 'User-Agent': 'MemoryVault/1.0 (public-source importer)', 'Accept': accept, 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader('Location')
                if not location:
                    raise HTTPException(422, 'The source returned an invalid redirect.')
                url = urljoin(normalized, location)
                continue
            if response.status in {401, 403, 429}:
                raise HTTPException(422, 'This source requires access or is rate limited. Import only content you can access; save its text as a note instead.')
            if response.status != 200:
                raise HTTPException(422, 'The public source could not be retrieved (HTTP '+str(response.status)+').')
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise HTTPException(422, 'This source uses an unsupported transfer encoding. Save its text as a note instead.')
            length = response.getheader('Content-Length')
            if length and (not length.isdigit() or int(length) > MAX_SOURCE_BYTES):
                raise HTTPException(413, 'Source exceeds the 2 MB import limit.')
            data = response.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise HTTPException(413, 'Source exceeds the 2 MB import limit.')
            return normalized, response.getheader('Content-Type', '').lower(), data
        except (OSError, http.client.HTTPException, UnicodeError):
            raise HTTPException(422, 'Unable to read this public source. Check its URL and try again.')
        finally:
            conn.close()
    raise HTTPException(422, 'This source redirects too many times.')


def page_text(url: str):
    final, mime, data = fetch_public(url)
    if mime.split(';')[0] not in {'text/html', 'application/xhtml+xml', 'text/plain'}:
        raise HTTPException(422, 'Only HTML articles and plain text can be imported. Upload documents through Add files.')
    if mime.startswith('text/plain'):
        title = urlsplit(final).hostname or 'Web memory'
        text = data.decode('utf-8', errors='replace')
    else:
        soup = BeautifulSoup(data, 'html.parser')
        title = soup.title.get_text(' ', strip=True) if soup.title else (urlsplit(final).hostname or 'Web memory')
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'form', 'iframe', 'noscript', 'svg', 'button']):
            element.decompose()
        body = soup.find('article') or soup.find('main') or soup.body or soup
        text = '\n'.join(line.strip() for line in body.get_text('\n', strip=True).splitlines() if line.strip())
    if len(text.strip()) < 30:
        raise HTTPException(422, 'This page has no readable article text. Pages requiring JavaScript or a login can be saved as a note instead.')
    if len(text) > 200000:
        raise HTTPException(413, 'Article exceeds the 200,000 character limit.')
    return title[:255], text, final


def github_readme(url: str):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'github.com', 'www.github.com'} or parsed.username or parsed.password or parsed.port or parsed.query:
        raise HTTPException(422, 'Use a public repository URL such as https://github.com/owner/repository.')
    parts = parsed.path.strip('/').removesuffix('.git').split('/')
    if len(parts) != 2 or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p) or p in {'.', '..'} for p in parts):
        raise HTTPException(422, 'Use the repository root URL. This importer saves the public README, not the entire repository.')
    owner, repo = parts
    _, mime, data = fetch_public(f'https://api.github.com/repos/{owner}/{repo}/readme', 'application/vnd.github+json')
    try:
        item = json.loads(data)
        if item['encoding'] != 'base64' or item.get('size', MAX_SOURCE_BYTES+1) > 200000:
            raise ValueError()
        text = base64.b64decode(item['content'], validate=False).decode('utf-8')
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise HTTPException(422, 'This repository has no supported public README. Save a documentation page instead.')
    if not text.strip() or len(text) > 200000:
        raise HTTPException(422, 'The README is empty or too large.')
    return f'{owner}/{repo} — README'[:255], text, f'https://github.com/{owner}/{repo}'


class ImportInput(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    kind: Literal['webpage', 'github', 'youtube'] = 'webpage'
    transcript: str = Field(default='', max_length=200000)

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        value = value.strip()
        try:
            parsed = urlsplit(value)
            port = parsed.port
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or any(ord(c) < 33 for c in value):
                raise ValueError()
        except ValueError:
            raise ValueError('Use a valid public HTTP or HTTPS URL without embedded credentials.')
        return value


def youtube_text(body: ImportInput):
    parsed = urlsplit(body.url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port:
        raise HTTPException(422, 'Use a public HTTPS YouTube watch or short URL.')
    if parsed.hostname in {'www.youtube.com', 'youtube.com'} and parsed.path == '/watch':
        video = parse_qs(parsed.query).get('v', [''])[0]
    elif parsed.hostname == 'youtu.be':
        video = parsed.path.strip('/')
    else:
        video = ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        raise HTTPException(422, 'Use a valid YouTube watch or short URL.')
    if len(body.transcript.strip()) < 30:
        raise HTTPException(422, 'Automatic transcript access is not configured. Paste an available transcript from the video to save and search it; no video content has been imported yet.')
    return 'YouTube transcript — '+video, body.transcript.strip(), 'https://www.youtube.com/watch?v='+video


@router.post('/imports', status_code=201)
def import_source(body: ImportInput, tasks: BackgroundTasks, user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]):
    rate_limit('import:'+user.id, 10)
    if body.kind == 'webpage':
        title, text, source = page_text(body.url)
    elif body.kind == 'github':
        title, text, source = github_readme(body.url)
    else:
        title, text, source = youtube_text(body)
    payload = text.encode('utf-8')
    check_quota(db, user.id, len(payload))
    digest = hashlib.sha256(payload).hexdigest()
    if db.scalar(select(Document.id).where(Document.user_id == user.id, Document.digest == digest)):
        raise HTTPException(409, 'This source content is already in your vault.')
    doc = Document(id=uid(), user_id=user.id, title=title, kind='link', format='md' if body.kind == 'github' else 'txt', size=len(payload), digest=digest, source_url=source, source_type=body.kind)
    doc.key = user.id+'/'+doc.id
    try:
        storage.put(doc.key, payload)
    except Exception:
        raise HTTPException(503, 'Storage unavailable. The import was not saved.')
    db.add(doc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(doc.key)
        raise
    enqueue(doc.id, tasks)
    # Delayed import avoids a circular router dependency.
    from .main import doc_json
    return doc_json(doc, True)
