"""Exercise real local models and OCR against a disposable MemoryVault account/database."""
from pathlib import Path
import asyncio,io,json,math,os,subprocess,sys,tempfile,time
from datetime import datetime,timezone
from local_ai_runtime import ROOT,CHAT_MODEL,EMBED_MODEL,local_service
sys.path.insert(0,str(ROOT/'services/api'))
report={'started_at':datetime.now(timezone.utc).isoformat(),'tests':{},'private_vault_modified':False}
(ROOT/'work/tmp').mkdir(parents=True,exist_ok=True)
(ROOT/'work/ai-reports').mkdir(parents=True,exist_ok=True)
test_root=Path(tempfile.mkdtemp(prefix='local-ai-verification-',dir=ROOT/'work/tmp'))
records=json.loads((ROOT/'local-ai-models.lock.json').read_text())['models']
revision=next(x['manifest_sha256'] for x in records if x['model']==EMBED_MODEL)
os.environ.update({'DATABASE_URL':'sqlite:///'+(test_root/'test.db').as_posix(),'DATA_DIR':str(test_root/'storage'),'APP_ORIGIN':'http://localhost:3000','COOKIE_SECURE':'false','STORAGE_BACKEND':'local','REDIS_URL':'','MAIL_MODE':'local','SMTP_HOST':'','EMBEDDING_BACKEND':'ollama','EMBEDDING_MODEL':EMBED_MODEL,'EMBEDDING_MODEL_REVISION':revision,'EMBEDDING_DIMENSIONS':'384','EMBEDDING_BATCH_SIZE':'8','EMBEDDING_KEEP_ALIVE_SECONDS':'300','EMBEDDING_TIMEOUT_SECONDS':'240','LLM_PROVIDER':'ollama','LLM_MODEL':CHAT_MODEL,'LLM_API_KEY':'','LLM_CONTEXT_LENGTH':'8192','LLM_MAX_OUTPUT_TOKENS':'1536','LLM_KEEP_ALIVE_SECONDS':'300','LLM_REQUEST_TIMEOUT_SECONDS':'240','TESSERACT_CMD':str(ROOT/'work/ai-runtime/tesseract-5.5.3/tesseract.exe'),'TESSDATA_PREFIX':str(ROOT/'work/ai-runtime/tesseract-5.5.3/tessdata'),'OCR_LANGUAGE':'eng'})
def record(name,value):
 report['tests'][name]=value
 (ROOT/'work/ai-reports/backend-local-ai.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(name+': '+json.dumps(value,ensure_ascii=True),flush=True)
def good(response,code=200):
 if response.status_code!=code:raise AssertionError(f'{response.request.url.path}: {response.status_code} {response.text[:600]}')
 return response.json()
try:
 with local_service('backend-local-ai.log',loaded_models=2) as service:
  os.environ.update({'EMBEDDING_BASE_URL':service.base,'LLM_BASE_URL':service.base})
  from fastapi.testclient import TestClient
  from sqlalchemy import select
  from app.main import app
  from app.db import Base,engine,DB,Chunk
  from app import ai
  from PIL import Image,ImageDraw,ImageFont
  Base.metadata.create_all(engine)
  record('runtime',service.api('/api/version'))
  with TestClient(app) as client:
   user=good(client.post('/api/v1/auth/register',json={'email':'local-model-test@example.test','name':'Local model verification','password':'Local-model-test-password-2026'}),201)
   client.headers['X-CSRF-Token']=user['csrf']
   start=time.monotonic()
   created=good(client.post('/api/v1/notes',json={'title':'Atlas review plan','content':'Project Atlas has its review on 12 November 2026 at 3 PM in the Cedar room. Mira will present the solar battery results. The battery held 84 percent charge after 100 cycles. The team uses spaced practice to revisit important ideas over several days.','tags':['atlas','learning']}),201)
   note_id=created['id'];doc=good(client.get('/api/v1/documents/'+note_id));assert doc['status']=='ready',doc.get('error')
   record('note_ingestion',{'passed':True,'seconds':round(time.monotonic()-start,3)})
   pdf=(ROOT/'apps/web/e2e/fixtures/photosynthesis.pdf').read_bytes()
   created=good(client.post('/api/v1/uploads',files={'file':('photosynthesis.pdf',pdf,'application/pdf')}),201);pdf_id=created['id']
   doc=good(client.get('/api/v1/documents/'+pdf_id));assert doc['status']=='ready',doc.get('error')
   with DB() as db:
    chunks=list(db.scalars(select(Chunk)))
    assert chunks and all(len(c.embedding)==384 and math.isclose(sum(v*v for v in c.embedding),1,abs_tol=1e-5) for c in chunks)
    assert all(revision in c.model for c in chunks)
   record('pdf_and_vectors',{'passed':True,'chunks':len(chunks),'dimensions':384,'normalized':True,'revision_pinned':True})
   results=good(client.get('/api/v1/search',params={'q':'How do green organisms produce nourishment?'}))['items']
   assert results and results[0]['document_id']==pdf_id,results
   record('semantic_paraphrase_search',{'passed':True,'top_title':results[0]['title'],'score':results[0]['score']})
   start=time.monotonic();chat=good(client.post('/api/v1/chat',json={'question':'How does photosynthesis work? Cite the passage.','document_id':pdf_id}))
   answer=chat['message']['content'];assert 'sunlight' in answer.lower() and '[1]' in answer,answer
   assert chat['message']['citations'][0]['document_id']==pdf_id
   record('grounded_document_qa',{'passed':True,'seconds':round(time.monotonic()-start,3),'answer':answer})
   follow=good(client.post('/api/v1/chat',json={'question':'What kind of energy does that process produce?','document_id':pdf_id,'conversation_id':chat['conversation_id']}))
   assert 'chemical' in follow['message']['content'].lower(),follow
   record('conversation_context',{'passed':True,'answer':follow['message']['content']})
   response=client.post('/api/v1/chat/stream',json={'question':'When and where is the Project Atlas review?','document_id':note_id})
   assert response.status_code==200 and 'event: done' in response.text and 'event: error' not in response.text,response.text[:500]
   assert '3 PM' in response.text or '3 pm' in response.text.lower()
   assert response.text.count('event: token') > 1
   record('streaming',{'passed':True,'real_token_events':response.text.count('event: token'),'completion_event':True})
   start=time.monotonic();insight=good(client.post('/api/v1/documents/'+note_id+'/insights'))
   record('structured_insights',{'passed':True,'seconds':round(time.monotonic()-start,3),'summary':insight.get('summary',insight.get('insight',{}).get('summary',''))})
   study=good(client.post('/api/v1/study/'+note_id));assert study['cards'] and all(c['citation']['document_id']==note_id for c in study['cards'])
   record('grounded_flashcards',{'passed':True,'cards':len(study['cards'])})
   quiz=good(client.post('/api/v1/quizzes/'+note_id),201);assert quiz['questions']
   record('structured_quiz',{'passed':True,'questions':len(quiz['questions'])})
   combined=good(client.post('/api/v1/chat',json={'question':'What energy does photosynthesis produce, and when is the Atlas review? Use both saved sources.'}))
   content=combined['message']['content'].lower()
   assert 'chemical' in content and ('3 pm' in content or '15:00' in content),combined
   assert len({c['document_id'] for c in combined['message']['citations']}) >= 2
   record('cross_document_qa',{'passed':True,'answer':combined['message']['content']})
   conflicting=good(client.post('/api/v1/notes',json={'title':'Atlas alternative schedule','content':'Project Atlas has its review on 12 November 2026 at 5 PM in the Cedar room. Mira will present the solar battery results.'}),201)
   compared=good(client.post('/api/v1/contradictions',json={'document_ids':[note_id,conflicting['id']]}))
   assert compared['items'],compared
   record('contradiction_review',{'passed':True,'conflicts':len(compared['items']),'quotes_verified_by_backend':True})
   unknown=asyncio.run(ai.generate('What is the review organizer\'s phone number?',[{'title':'Plan','text':'The Atlas review is on 12 November at 3 PM.'}]))
   assert any(x in unknown.lower() for x in ['not provided','not contain','insufficient','no information','not mentioned','not include','cannot','don\'t have']),unknown
   record('insufficient_evidence',{'passed':True,'answer':unknown})
   image=Image.new('RGB',(1400,350),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',40)
   draw.multiline_text((40,40),'SCAN VERIFICATION\nThe Orion meeting starts at 4 PM on Monday.\nBring the research notebook.',font=font,fill='black',spacing=20)
   scanned=io.BytesIO();image.save(scanned,format='PDF',resolution=150)
   scan=good(client.post('/api/v1/uploads',files={'file':('scanned-review.pdf',scanned.getvalue(),'application/pdf')}),201)
   scan_doc=good(client.get('/api/v1/documents/'+scan['id']));assert scan_doc['status']=='ready',scan_doc.get('error');assert '4 PM' in scan_doc['content']
   record('scanned_pdf_to_search',{'passed':True,'page_text_recognized':True})
   with TestClient(app) as other:
    account=good(other.post('/api/v1/auth/register',json={'email':'other-local-test@example.test','name':'Other','password':'Different-test-password-2026'}),201)
    assert other.get('/api/v1/documents/'+note_id).status_code==404
    assert good(other.get('/api/v1/search',params={'q':'Atlas review'}))['items']==[]
   record('semantic_account_isolation',{'passed':True})
  report['residency']=service.api('/api/ps')
  assert all(m['size_vram']==m['size'] for m in report['residency']['models']),report['residency']
  assert any(m['model']==CHAT_MODEL and m['context_length']==8192 for m in report['residency']['models'])
  report['gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,memory.free,driver_version','--format=csv'],text=True).strip()
  report['passed']=True
except Exception as error:
 report['passed']=False;report['error']=f'{type(error).__name__}: {error}';print(report['error'],flush=True);raise
finally:
 report['finished_at']=datetime.now(timezone.utc).isoformat();report['test_data_directory']=str(test_root)
 (ROOT/'work/ai-reports/backend-local-ai.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('Verification report:',ROOT/'work/ai-reports/backend-local-ai.json',flush=True)
