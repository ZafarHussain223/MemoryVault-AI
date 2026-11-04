'use client';
import { useState } from 'react';
import { ArrowUpRight, Link as LinkIcon, LoaderCircle } from 'lucide-react';
import { Doc, post } from '@/lib/api';
export default function ImportMemory({ onImported }: {
    onImported: (document: Doc) => void;
}) {
    const [kind, setKind] = useState('webpage'), [url, setUrl] = useState(''), [transcript, setTranscript] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
    async function submit(event: React.FormEvent) { event.preventDefault(); setBusy(true); setError(''); try {
        const doc = await post<Doc>('/imports', { kind, url, transcript: kind === 'youtube' ? transcript : undefined });
        setUrl('');
        setTranscript('');
        onImported(doc);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : 'This source could not be imported.');
    }
    finally {
        setBusy(false);
    } }
    return <form className="import-memory" onSubmit={submit}><div className="section-header"><h3><LinkIcon size={17}/> SAVE A SOURCE</h3><span className="mono">FROM THE WEB</span></div><p className="muted">Keep the useful parts of a public source alongside your own notes.</p><label>Source type<select value={kind} onChange={e => setKind(e.target.value)} disabled={busy}><option value="webpage">Public webpage</option><option value="github">Public GitHub repository README</option><option value="youtube">YouTube transcript</option></select></label><label>Source URL<input type="url" required value={url} onChange={e => setUrl(e.target.value)} placeholder={kind === 'github' ? 'https://github.com/owner/repository' : kind === 'youtube' ? 'https://www.youtube.com/watch?v=…' : 'https://example.com/article'} maxLength={2048} disabled={busy}/></label>{kind === 'youtube' && <label>Video transcript<textarea rows={7} required value={transcript} onChange={e => setTranscript(e.target.value)} maxLength={200000} placeholder="Paste an available transcript that you have permission to save."/><small className="fine-print">Automatic transcript retrieval is not available. Paste the transcript from the video to make its content searchable.</small></label>}<p className="fine-print">Public text only. Sign-in pages, private network addresses, and protected sources cannot be imported. YouTube saves the transcript you provide.</p><button className="button orange" disabled={busy || !url.trim()}>{busy ? <><LoaderCircle size={16} className="spin"/> READING SOURCE…</> : <>SAVE TO VAULT <ArrowUpRight size={16}/></>}</button>{error && <p className="error" role="alert">{error}</p>}</form>;
}
