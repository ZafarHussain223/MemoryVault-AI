"""Regression tests for original files, full text, and complete long-document indexing."""
import io,json,zipfile
import pytest
from sqlalchemy import select,delete,insert
from fastapi.testclient import TestClient
from test_workflows import client,database,register,note
from app.main import app
from app.db import DB,Document,Chunk
from app import processing,config,search


def zipped(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,text in files.items():z.writestr(name,text)
    return out.getvalue()


def pptx_fixture():
    return zipped({'ppt/presentation.xml':'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="r1"/><p:sldId id="257" r:id="r2"/></p:sldIdLst></p:presentation>',
    'ppt/_rels/presentation.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="slides/slide1.xml" Type="slide"/><Relationship Id="r2" Target="slides/slide2.xml" Type="slide"/></Relationships>',
    'ppt/slides/slide1.xml':'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>Solar energy first slide</a:t></a:r></a:p></root>',
    'ppt/slides/slide2.xml':'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>Final slide turbine marker</a:t></a:r></a:p></root>',
    'ppt/slides/_rels/slide2.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="notes" Target="../notesSlides/notesSlide1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"/></Relationships>',
    'ppt/notesSlides/notesSlide1.xml':'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>Presenter secret orchid</a:t></a:r></a:p></root>'})


def test_pptx_slides_notes_original_ranges_and_owner_isolation(client):
    register(client);data=pptx_fixture()
    response=client.post('/api/v1/uploads',files={'file':('lesson.pptx',data)})
    assert response.status_code==201,response.text
    doc_id=response.json()['id'];doc=client.get('/api/v1/documents/'+doc_id).json()
    assert doc['status']=='ready',doc['error']
    assert 'Presenter secret orchid' in doc['content'] and 'Final slide' in doc['content']
    assert doc['indexed_pages']==2
    assert client.get('/api/v1/search?q=turbine&format=pptx').json()['items'][0]['page']==2
    original=client.get('/api/v1/documents/'+doc_id+'/original',headers={'Range':'bytes=0-15'})
    assert original.status_code==206 and original.content==data[:16]
    assert original.headers['x-frame-options']=='SAMEORIGIN'
    assert client.get('/api/v1/documents/'+doc_id+'/download').content==data
    with TestClient(app) as other:
        register(other,'other-viewer@example.test')
        for suffix in ['original','preview','text']:
            assert other.get('/api/v1/documents/'+doc_id+'/'+suffix).status_code==404


def test_large_text_full_pagination_and_original_preserved(client):
    register(client);text='Chapter one. '+'knowledge memory '*24000+'\nTHE FINAL COMPLETE BOOK MARKER'
    response=client.post('/api/v1/uploads',files={'file':('long-book.txt',text.encode())})
    assert response.status_code==201,response.text
    doc_id=response.json()['id'];doc=client.get('/api/v1/documents/'+doc_id).json()
    assert doc['status']=='ready' and doc['word_count']>20000
    offset=0;parts=[]
    while True:
        result=client.get(f'/api/v1/documents/{doc_id}/text?offset={offset}&limit=20000').json()
        parts.append(result['text'])
        if result['complete']:break
        assert result['next_offset']>offset;offset=result['next_offset']
    assert ''.join(parts)==text
    assert client.get('/api/v1/documents/'+doc_id+'/original').content==text.encode()
    saved=client.patch('/api/v1/documents/'+doc_id,json={'title':'Complete book renamed','tags':['book'],'content':'','version':doc['version']})
    assert saved.status_code==200 and saved.json()['content']==text
    assert saved.json()['word_count']==doc['word_count']
    assert saved.json()['indexed_chunks']==doc['indexed_chunks']
    assert client.get('/api/v1/documents/'+doc_id+'/text?offset=999999999').status_code==416


def test_active_html_is_shown_as_plain_text(client):
    register(client);data=b'<h1>Research</h1><script>alert(1)</script>'
    response=client.post('/api/v1/uploads',files={'file':('research.html',data)})
    assert response.status_code==201,response.text
    original=client.get('/api/v1/documents/'+response.json()['id']+'/original')
    assert original.content==data and original.headers['content-type'].startswith('text/plain')
    assert 'sandbox' in original.headers['content-security-policy']
    assert original.headers['x-content-type-options']=='nosniff'


def test_330_page_pdf_keeps_last_page_and_over_20000_words(client):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    writer=PdfWriter()
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    font_ref=writer._add_object(font)
    for i in range(330):
        page=writer.add_blank_page(612,792)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font_ref})})
        lines=[' '.join(['chapter','knowledge','memory','complete']*4)]*5
        lines.insert(0,f'Page {i+1} '+('FINALORCHIDMARKER' if i==329 else 'BOOKCONTENT'))
        stream=DecodedStreamObject();stream.set_data(('BT /F1 10 Tf 30 750 Td 14 TL '+' '.join('('+line+') Tj T*' for line in lines)+' ET').encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    out=io.BytesIO();writer.write(out);data=out.getvalue()
    register(client);response=client.post('/api/v1/uploads',files={'file':('330-page-book.pdf',data)})
    assert response.status_code==201,response.text
    doc_id=response.json()['id'];doc=client.get('/api/v1/documents/'+doc_id).json()
    assert doc['status']=='ready',doc['error']
    assert doc['word_count']>20000 and doc['indexed_pages']==330
    assert 'FINALORCHIDMARKER' in doc['content']
    match=client.get('/api/v1/search?q=FINALORCHIDMARKER').json()['items'][0]
    assert match['page']==330
    original=client.get('/api/v1/documents/'+doc_id+'/original',headers={'Range':'bytes=-32'})
    assert original.status_code==206 and original.content==data[-32:]


def test_indexing_over_2000_chunks_batches_and_retains_old_chunks_on_failure(client,monkeypatch):
    register(client);doc_id=note(client)
    with DB() as db:
        doc=db.get(Document,doc_id);doc.content='passage '*310000;doc.status='pending';db.commit()
    batches=[]
    def fake_embed(texts):batches.append(len(texts));return [None]*len(texts)
    monkeypatch.setattr(processing,'embed',fake_embed)
    processing.process_document(doc_id)
    with DB() as db:
        assert db.get(Document,doc_id).status=='ready'
        before=[c.id for c in db.scalars(select(Chunk).where(Chunk.document_id==doc_id))]
        assert len(before)>2000 and max(batches)<=128
        db.get(Document,doc_id).status='pending';db.commit()
    calls=0
    def incomplete(texts):
        nonlocal calls
        calls+=1
        return [None]*len(texts) if calls==1 else []
    monkeypatch.setattr(processing,'embed',incomplete);processing.process_document(doc_id)
    with DB() as db:
        assert db.get(Document,doc_id).status=='failed'
        assert [c.id for c in db.scalars(select(Chunk).where(Chunk.document_id==doc_id))]==before


def test_late_semantic_passage_after_5000_is_searchable(client,monkeypatch):
    register(client);doc_id=note(client)
    with DB() as db:
        owner=db.get(Document,doc_id).user_id;db.execute(delete(Chunk).where(Chunk.document_id==doc_id))
        rows=[{'document_id':doc_id,'ordinal':i,'text':'Unrelated passage','embedding':[-1.0]+[0.0]*383,'model':'test-current'} for i in range(5001)]
        rows[-1]['text']='Late relevant information';rows[-1]['embedding']=[1.0]+[0.0]*383
        db.execute(insert(Chunk),rows);db.commit()
    monkeypatch.setattr(search,'embeddings_enabled',lambda:True)
    monkeypatch.setattr(search,'model_identity',lambda:'test-current')
    monkeypatch.setattr(search,'embed',lambda *a,**k:[[1.0]+[0.0]*383])
    with DB() as db:
        found=search.retrieve(db,owner,'synonym')
        assert len(found)==1 and found[0]['text']=='Late relevant information'


def test_office_preview_is_cached_private_and_deleted_with_original(client,monkeypatch):
    from app import document_files,storage
    register(client);data=pptx_fixture()
    doc_id=client.post('/api/v1/uploads',files={'file':('slides.pptx',data)}).json()['id']
    calls=[];pdf=b'%PDF-1.4\nPrivate preview\n%%EOF'
    def convert(*args):calls.append(args);return pdf
    monkeypatch.setattr(document_files,'convert_office',convert)
    preview=client.get(f'/api/v1/documents/{doc_id}/preview',headers={'Range':'bytes=0-4'})
    assert preview.status_code==206 and preview.content==b'%PDF-'
    assert preview.headers['x-frame-options']=='SAMEORIGIN' and 'no-store' in preview.headers['cache-control']
    # A PDF reader can request many ranges without reconverting or exhausting
    # the conversion rate limit.
    for _ in range(25):
        assert client.get(f'/api/v1/documents/{doc_id}/preview',headers={'Range':'bytes=-5'}).status_code==206
    assert len(calls)==1
    with DB() as db:key=db.get(Document,doc_id).key
    assert storage.preview_path(key).is_file()
    with TestClient(app) as other:
        register(other,'cached-preview@example.test')
        assert other.get(f'/api/v1/documents/{doc_id}/preview').status_code==404
    assert client.delete(f'/api/v1/documents/{doc_id}').status_code==200
    assert not storage.preview_path(key).exists() and not storage.local_path(key).exists()
    assert client.get(f'/api/v1/documents/{doc_id}/preview').status_code==404


def test_epub_spine_order_complete_appendix_and_safe_rtf():
    from app.document_formats import extract_other,validate
    data=zipped({'mimetype':'application/epub+zip',
        'META-INF/container.xml':'<container><rootfiles><rootfile full-path="book/content.opf"/></rootfiles></container>',
        'book/content.opf':'<package><manifest><item id="second" href="second.html" media-type="text/html"/><item id="first" href="first.html" media-type="text/html"/><item id="appendix" href="appendix.html" media-type="text/html"/></manifest><spine><itemref idref="first"/><itemref idref="second"/></spine></package>',
        'book/first.html':'<h1>First chapter</h1><script>UNSAFE SCRIPT TEXT</script>',
        'book/second.html':'<p>Last spine chapter</p>',
        'book/appendix.html':'<p>Complete appendix orchid</p>'})
    validate(data,'epub');pages=extract_other(data,'epub')
    assert pages==[(1,'First chapter'),(2,'Last spine chapter'),(3,'Complete appendix orchid')]
    rtf=br'{\rtf1\ansi First paragraph\par Unicode \u945? and final orchid}'
    validate(rtf,'rtf');text=extract_other(rtf,'rtf')[0][1]
    assert 'First paragraph' in text and '\u03b1' in text and 'final orchid' in text


@pytest.mark.parametrize('data,extension',[
    (b'<!DOCTYPE x [<!ENTITY e "payload">]><x>&e;</x>','xml'),
    ('<!DOCTYPE x [<!ENTITY e "payload">]><x>&e;</x>'.encode('utf-16'),'xml'),
    (zipped({'../escape.xml':'<x/>','word/document.xml':'<x/>'}),'docx'),
    (b'fake binary office contents','ppt'),
])
def test_unsafe_or_mismatched_containers_are_rejected(data,extension):
    from app.document_formats import validate
    with pytest.raises(ValueError):validate(data,extension)


def test_extracted_text_limit_preserves_original_without_partial_index(client,monkeypatch):
    register(client);monkeypatch.setattr(config,'MAX_EXTRACTED_CHARS',20)
    data=b'This complete original is over the test text limit.'
    result=client.post('/api/v1/uploads',files={'file':('over-limit.txt',data)})
    assert result.status_code==201
    doc_id=result.json()['id'];doc=client.get('/api/v1/documents/'+doc_id).json()
    assert doc['status']=='failed' and 'nothing was partially indexed' in doc['error']
    assert doc['indexed_chunks']==0
    assert client.get('/api/v1/documents/'+doc_id+'/original').content==data


def test_mixed_pdf_page_does_not_hide_scanned_body_behind_native_footer(monkeypatch):
    pymupdf=pytest.importorskip('pymupdf')
    from PIL import Image
    from app import ocr
    image=io.BytesIO();Image.new('RGB',(300,400),'white').save(image,format='PNG')
    with pymupdf.open() as pdf:
        page=pdf.new_page()
        page.insert_image(pymupdf.Rect(20,20,400,600),stream=image.getvalue())
        page.insert_text((30,750),'Page 330')
        data=pdf.tobytes()
    calls=[]
    def recognize(image):calls.append(image.size);return 'Scanned body FINAL ORCHID\nPage 330\n'
    monkeypatch.setattr(ocr,'read_image',recognize)
    pages=processing.extract(data,'pdf')
    assert len(calls)==1 and len(pages)==1 and pages[0][0]==1
    assert 'Scanned body FINAL ORCHID' in pages[0][1]
    assert pages[0][1].count('Page 330')==1
    monkeypatch.setattr(config,'MAX_OCR_PAGES',0)
    with pytest.raises(ValueError,match='nothing was partially indexed'):processing.extract(data,'pdf')
    # The lightweight fallback must report missing OCR, even when a native
    # footer exists, instead of marking that footer as the whole document.
    import builtins
    real_import=builtins.__import__
    def without_pymupdf(name,*args,**kwargs):
        if name=='pymupdf':raise ImportError('test missing optional parser')
        return real_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',without_pymupdf)
    with pytest.raises(ValueError,match='need OCR'):processing.extract(data,'pdf')
