'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {LoaderCircle,RotateCcw,Save,Check} from 'lucide-react';
import {api,Doc,APIError} from '@/lib/api';
import MarkdownEditor from './MarkdownEditor';

type Draft={title:string;content:string;tags:string};
const fromDocument=(document:Doc):Draft=>({title:document.title,content:document.kind==='note'?(document.content||''):'',tags:document.tags.join(', ')});
const cleanTags=(tags:string)=>Array.from(new Set(tags.split(',').map(tag=>tag.trim().toLowerCase()).filter(Boolean)));
const differs=(draft:Draft,document:Doc)=>draft.title!==document.title||(document.kind==='note'&&draft.content!==(document.content||''))||JSON.stringify(cleanTags(draft.tags))!==JSON.stringify(document.tags);

export default function DocumentEditor({document,onSaved,onDirtyChange,onBusyChange}:{document:Doc;onSaved:(document:Doc)=>void;onDirtyChange:(dirty:boolean)=>void;onBusyChange:(busy:boolean)=>void}){
 const [base,setBase]=useState(document),[draft,setDraft]=useState<Draft>(()=>fromDocument(document)),[busy,setBusy]=useState(false),[error,setError]=useState(''),[paused,setPaused]=useState(false),[saved,setSaved]=useState(false);
 const saving=useRef(false),latest=useRef(draft),baseRef=useRef(base),callbacks=useRef({onSaved,onDirtyChange,onBusyChange});
 latest.current=draft;baseRef.current=base;callbacks.current={onSaved,onDirtyChange,onBusyChange};
 const dirty=differs(draft,base);
 useEffect(()=>{callbacks.current.onDirtyChange(dirty);callbacks.current.onBusyChange(busy)},[dirty,busy]);
 useEffect(()=>()=>{callbacks.current.onDirtyChange(false);callbacks.current.onBusyChange(false)},[]);
 useEffect(()=>{if(!dirty&&!busy)return;const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty,busy]);
 useEffect(()=>{if(document.version===baseRef.current.version){setBase(previous=>({...previous,status:document.status}));return}if(differs(latest.current,baseRef.current)){setError('This memory changed while you were editing. Your draft is still here. Copy it before reloading the saved version.');setPaused(true)}else{setBase(document);setDraft(fromDocument(document))}},[document.id,document.version,document.status]);
 useEffect(()=>{if(!['pending','processing'].includes(base.status))return;let active=true;const timer=setInterval(async()=>{try{const fresh=await api<Doc>('/documents/'+base.id);if(active&&!saving.current){
   if(fresh.version!==baseRef.current.version&&differs(latest.current,baseRef.current)){
    setError('This memory changed in another tab. Your draft has been preserved. Copy it before reloading the saved version.');setPaused(true);
    setBase(previous=>({...previous,status:fresh.status}));
   }else{setBase(fresh);if(fresh.version!==baseRef.current.version)setDraft(fromDocument(fresh))}
   callbacks.current.onSaved(fresh);
  }}catch{/* A regular save or explicit reload surfaces actionable errors. */}},2000);return()=>{active=false;clearInterval(timer)}},[base.id,base.status]);
 const save=useCallback(async()=>{
  const snapshot=latest.current,current=baseRef.current;
  if(saving.current||!differs(snapshot,current))return;
  if(!snapshot.title.trim()){setError('Give this memory a title before saving.');setPaused(true);return}
  if(cleanTags(snapshot.tags).length>30){setError('Use up to 30 tags per memory.');setPaused(true);return}
  saving.current=true;setBusy(true);setError('');setSaved(false);
  try{
   const fresh=await api<Doc>('/documents/'+current.id,{method:'PATCH',body:JSON.stringify({title:snapshot.title,content:current.kind==='note'?snapshot.content:'',tags:cleanTags(snapshot.tags),version:current.version})});
   // Only update the saved baseline. Keystrokes typed during this request remain
   // in the draft and are saved by the next debounced pass.
   baseRef.current=fresh;setBase(fresh);setSaved(true);setPaused(false);callbacks.current.onSaved(fresh);
  }catch(reason){setError(reason instanceof APIError&&reason.status===409?reason.message+' Your draft has been preserved.':reason instanceof Error?reason.message:'This draft could not be saved.');setPaused(true)}
  finally{saving.current=false;setBusy(false)}
 },[]);
 useEffect(()=>{if(base.kind!=='note'||!dirty||busy||paused||base.status!=='ready')return;const timer=setTimeout(()=>void save(),1100);return()=>clearTimeout(timer)},[draft,base,dirty,busy,paused,save]);
 async function reload(){if(dirty&&!confirm('Reload the saved version and discard this unsaved draft?'))return;setBusy(true);setError('');try{const fresh=await api<Doc>('/documents/'+base.id);setBase(fresh);setDraft(fromDocument(fresh));setPaused(false);setSaved(false);callbacks.current.onSaved(fresh)}catch(reason){setError(reason instanceof Error?reason.message:'The saved version could not be loaded.')}finally{setBusy(false)}}
 return <form onSubmit={event=>{event.preventDefault();void save()}} className="document-editor"><label>Title<input required maxLength={255} value={draft.title} onChange={event=>{setDraft(previous=>({...previous,title:event.target.value}));setSaved(false)}}/></label><label>Tags, separated by commas<input value={draft.tags} onChange={event=>{setDraft(previous=>({...previous,tags:event.target.value}));setSaved(false)}}/></label>{base.kind==='note'?<MarkdownEditor label="Markdown note" value={draft.content} onChange={content=>{setDraft(previous=>({...previous,content}));setSaved(false)}} rows={8}/>:null}<div className="editor-save-row"><button className="button compact" disabled={busy||base.status==='processing'||!dirty}>{busy?<LoaderCircle className="spin" size={14}/>:<Save size={14}/>} {busy?'SAVING…':'SAVE CHANGES'}</button><span className="mono autosave-status" role="status">{busy?'Saving your draft':saved&&!dirty?<><Check size={12}/> Saved</>:base.kind==='note'?(paused?'Automatic save paused':dirty?(base.status==='ready'?'Saving shortly…':'Waiting for indexing…'):'Automatic save on'):(dirty?'Unsaved changes':'Up to date')}</span></div>{error&&<div className="editor-error"><p className="error" role="alert">{error}</p><button className="text-button" type="button" disabled={busy} onClick={reload}><RotateCcw size={13}/> RELOAD SAVED VERSION</button></div>}</form>;
}
