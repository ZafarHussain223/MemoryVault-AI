'use client';
import {useEffect, useId, useRef, useState} from 'react';
import {ArrowLeft, ArrowRight, Download, ExternalLink, FileText, LoaderCircle, RotateCcw} from 'lucide-react';
import {api, Doc} from '@/lib/api';
import styles from './DocumentViewer.module.css';

const SECTION_SIZE = 20000;
const imageFormats = new Set(['png', 'jpg', 'jpeg', 'webp']);
const officeFormats = new Set(['doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'odt', 'ods', 'odp', 'rtf']);
const textFormats = new Set(['txt', 'md', 'csv', 'tsv', 'json', 'xml', 'html', 'htm', 'yaml', 'yml', 'log']);
type TextSection = {text:string; offset:number; next_offset:number|null; total_characters:number; complete:boolean};
type Tab = 'original'|'text';

/** Private, same-origin originals and bounded rendering of the complete extracted text. */
export default function DocumentViewer({document}:{document:Doc}) {
  const [tab,setTab] = useState<Tab>(document.kind === 'file' ? 'original' : 'text');
  const [offset,setOffset] = useState(0), [section,setSection] = useState<TextSection|null>(null);
  const [sectionInput,setSectionInput] = useState('1'), [textBusy,setTextBusy] = useState(false), [textError,setTextError] = useState('');
  const [previewBusy,setPreviewBusy] = useState(false), [previewReady,setPreviewReady] = useState(false), [previewError,setPreviewError] = useState('');
  const [retry,setRetry] = useState(0);
  const textArea=useRef<HTMLPreElement>(null), originalTab=useRef<HTMLButtonElement>(null), textTab=useRef<HTMLButtonElement>(null);
  const id=useId();
  const format=document.format.toLowerCase(), hasOriginal=document.kind==='file';
  const image=imageFormats.has(format), office=officeFormats.has(format), plain=textFormats.has(format);
  const canPreview=format==='pdf'||image||office||plain;
  const base='/api/v1/documents/'+encodeURIComponent(document.id);
  const originalUrl=base+'/original';
  const previewUrl=base+(office?'/preview':'/original')+'?version='+document.version;
  const total=section?.total_characters??document.content_characters??0;
  const sections=Math.max(1,Math.ceil(total/SECTION_SIZE));
  const currentSection=Math.floor(offset/SECTION_SIZE)+1;

  useEffect(()=>{setOffset(0);setSection(null);setSectionInput('1')},[document.id,document.version]);
  useEffect(()=>{
    if(tab!=='text')return;
    const controller=new AbortController();
    setTextBusy(true);setTextError('');
    api<TextSection>('/documents/'+document.id+'/text?offset='+offset+'&limit='+SECTION_SIZE,{signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted){setSection(result);setSectionInput(String(Math.floor(result.offset/SECTION_SIZE)+1));if(textArea.current)textArea.current.scrollTop=0}})
      .catch(reason=>{if(!controller.signal.aborted)setTextError(reason instanceof Error?reason.message:'The extracted text could not be loaded.')})
      .finally(()=>{if(!controller.signal.aborted)setTextBusy(false)});
    return()=>controller.abort();
  },[document.id,document.version,document.status,tab,offset,retry]);
  useEffect(()=>{
    if(tab!=='original'||!canPreview)return;
    const controller=new AbortController();
    setPreviewBusy(true);setPreviewReady(false);setPreviewError('');
    async function check(){
      try{
        // A one-byte probe lets the app display conversion/authentication errors
        // without downloading an entire book into a JavaScript Blob first.
        const response=await fetch(previewUrl,{headers:{Range:'bytes=0-0'},credentials:'same-origin',cache:'no-store',signal:controller.signal});
        if(!response.ok){let detail='The original preview could not be opened.';try{const body=await response.json();if(typeof body.detail==='string')detail=body.detail}catch{}throw new Error(detail)}
        const type=response.headers.get('content-type')||'';
        const valid=office||format==='pdf'?type.startsWith('application/pdf'):image?type.startsWith('image/'):type.startsWith('text/plain');
        await response.body?.cancel();
        if(!valid)throw new Error('This original is available to download. An inline preview is not available for its file type.');
        if(!controller.signal.aborted)setPreviewReady(true);
      }catch(reason){if(!controller.signal.aborted)setPreviewError(reason instanceof Error?reason.message:'The original preview could not be opened.')}
      finally{if(!controller.signal.aborted)setPreviewBusy(false)}
    }
    void check();return()=>controller.abort();
  },[tab,canPreview,previewUrl,office,format,image,retry]);

  function go(next:number){setOffset(Math.max(0,Math.min((sections-1)*SECTION_SIZE,next)))}
  function tabKeys(event:React.KeyboardEvent<HTMLButtonElement>){
    if(!hasOriginal||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();const next=event.key==='Home'?'original':event.key==='End'?'text':tab==='original'?'text':'original';setTab(next);
    (next==='original'?originalTab:textTab).current?.focus();
  }
  return <section className={styles.viewer} aria-label="Document reader">
    <div className={styles.heading}><div><span className="mono">YOUR SAVED SOURCE</span><h3>Read your document</h3></div><a className="text-button" href={base+'/download'}><Download size={14}/> DOWNLOAD ORIGINAL</a></div>
    <div className={styles.stats}>
      {document.word_count!==undefined&&<span>{document.word_count.toLocaleString()} extracted words</span>}
      {document.indexed_pages!==undefined&&document.indexed_pages>0&&<span>{document.indexed_pages.toLocaleString()} pages with indexed text</span>}
      {document.indexed_chunks!==undefined&&<span>{document.indexed_chunks.toLocaleString()} searchable passages</span>}
    </div>
    <div className={styles.tabs} role="tablist" aria-label="Document view">
      {hasOriginal&&<button type="button" ref={originalTab} role="tab" id={id+'-original-tab'} aria-controls={id+'-original-panel'} aria-selected={tab==='original'} tabIndex={tab==='original'?0:-1} onKeyDown={tabKeys} onClick={()=>setTab('original')}>Original</button>}
      <button type="button" ref={textTab} role="tab" id={id+'-text-tab'} aria-controls={id+'-text-panel'} aria-selected={tab==='text'} tabIndex={tab==='text'?0:-1} onKeyDown={tabKeys} onClick={()=>setTab('text')}>Extracted text</button>
    </div>
    {tab==='original'?<div role="tabpanel" id={id+'-original-panel'} aria-labelledby={id+'-original-tab'}>
      <div className={styles.previewInfo}><p>{office?'A private PDF rendering of your uploaded file. The download keeps the original format.':format==='pdf'?'The complete uploaded PDF, including its original pages and layout.':image?'The image exactly as saved in your vault.':plain?'The original file displayed as plain text.':'Your original file is preserved in its uploaded format.'}</p>{canPreview&&<a className="text-button" href={previewUrl} target="_blank" rel="noopener noreferrer">OPEN FULL VIEW <ExternalLink size={14}/></a>}</div>
      {previewBusy&&<div className={styles.loading} role="status"><LoaderCircle className="spin" size={20}/>{office?'Preparing your document preview…':'Opening the original file…'}</div>}
      {previewError&&<div className={styles.fallback}><p role="alert">{previewError}</p><p>Your original remains available to download. You can also read its extracted text in the other tab.</p><button type="button" className="text-button" onClick={()=>setRetry(value=>value+1)}><RotateCcw size={14}/> RETRY PREVIEW</button></div>}
      {!canPreview&&<div className={styles.fallback}><FileText size={26}/><p>Download the {format.toUpperCase()} original to open it in a compatible reader. Its extracted text is available here in the other tab.</p><a className="button compact" href={originalUrl}>OPEN ORIGINAL <ExternalLink size={14}/></a></div>}
      {previewReady&&(image?<div className={styles.imageFrame}><img src={previewUrl} alt={'Original uploaded image: '+document.title}/></div>:<iframe className={styles.frame} src={previewUrl} title={(office?'Document preview: ':'Original file: ')+document.title} sandbox={plain?'':undefined} data-testid="original-file-frame"/>)}
    </div>:<div role="tabpanel" id={id+'-text-panel'} aria-labelledby={id+'-text-tab'}>
      <p className={styles.explanation}>All extracted text is available in sections so long documents stay responsive. Section numbers describe this text view, not the original page numbers.</p>
      {document.status!=='ready'&&<p className="fine-print">{document.status==='failed'?'Indexing did not finish. Retry processing to make the full extracted text searchable. The uploaded original remains available.':'Text will appear when processing finishes. The uploaded original is already available.'}</p>}
      <div className={styles.pagination} aria-label="Extracted text navigation">
        <button className="button compact" type="button" disabled={textBusy||offset===0} onClick={()=>go(offset-SECTION_SIZE)}><ArrowLeft size={14}/> PREVIOUS</button>
        <form className={styles.jump} onSubmit={event=>{event.preventDefault();const value=Number(sectionInput);if(Number.isInteger(value)&&value>=1&&value<=sections)go((value-1)*SECTION_SIZE)}}><label>Text section<input aria-label="Text section" type="number" min={1} max={sections} step={1} value={sectionInput} onChange={event=>setSectionInput(event.target.value)} disabled={textBusy}/></label><span>of {sections.toLocaleString()}</span><button type="submit" className="text-button" disabled={textBusy}>GO</button></form>
        <div className={styles.nextActions}><button className="button compact" type="button" disabled={textBusy||!section||section.next_offset===null} onClick={()=>section?.next_offset!==null&&section?.next_offset!==undefined&&go(section.next_offset)}>NEXT <ArrowRight size={14}/></button><button className="text-button" type="button" disabled={textBusy||currentSection>=sections} onClick={()=>go((sections-1)*SECTION_SIZE)}>LAST SECTION</button></div>
      </div>
      {textBusy?<div className={styles.loading} role="status"><LoaderCircle className="spin" size={20}/> Loading text section…</div>:textError?<div className={styles.fallback}><p role="alert">{textError}</p><button type="button" className="text-button" onClick={()=>setRetry(value=>value+1)}>RETRY TEXT</button></div>:<>
        <p className={styles.range} role="status">{total?`Section ${currentSection.toLocaleString()} of ${sections.toLocaleString()} · characters ${(offset+1).toLocaleString()}–${Math.min(offset+SECTION_SIZE,total).toLocaleString()} of ${total.toLocaleString()}`:'No extracted text is available yet.'}</p>
        {section?.text&&<pre className={styles.text} ref={textArea} tabIndex={0} aria-label="Extracted document text">{section.text}</pre>}
      </>}
    </div>}
  </section>;
}
