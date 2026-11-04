'use client';

import { useEffect, useState } from 'react';
import { ArrowUpRight, Bookmark, RotateCcw, X } from 'lucide-react';
import { api, post, date, type Doc } from '@/lib/api';
import styles from './Engagement.module.css';

type Recall = Doc & { reason: string; reasons?: string[]; signals?: string[] };
export default function RecallPanel({ enabled, onSource }: { enabled: boolean; onSource: (id: string) => void }) {
    const [items, setItems] = useState<Recall[]>([]), [loaded, setLoaded] = useState(false), [error, setError] = useState(''), [busy, setBusy] = useState(''), [revision, setRevision] = useState(0);
    useEffect(() => {
        let active = true; setLoaded(false); setError('');
        api<Recall[]>('/recall').then(data => { if (active) setItems(data); })
            .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Could not load recommendations.'); })
            .finally(() => { if (active) setLoaded(true); });
        return () => { active = false; };
    }, [revision, enabled]);
    async function dismiss(id: string) {
        setBusy(id); setError('');
        try { await post('/recall/' + id + '/dismiss'); setItems(current => current.filter(item => item.id !== id)); }
        catch (e) { setError(e instanceof Error ? e.message : 'Could not dismiss this recommendation.'); }
        finally { setBusy(''); }
    }
    return <section>
        <div className="page-heading"><div><span className="mono label">[ SOMETHING WORTH REVISITING ]</span><h1>HELLO AGAIN,<br />GOOD IDEA.</h1><p>Follow a thread back to something you already know.</p></div><button className="button compact" disabled={!loaded || !!busy} onClick={() => setRevision(value => value + 1)}><RotateCcw size={14} /> REFRESH</button></div>
        <div className={styles.recallExplanation}><Bookmark size={21} /><p>Suggestions use saved tags, interests, explicit connections and visit history when enabled. Each memory tells you why it surfaced. Dismissed memories stay out of future suggestions.</p></div>
        {error && <p className="error" role="alert">{error}</p>}
        {!loaded ? <p className="muted" role="status">Looking for ideas worth another visit…</p> : items.length ? <div className={styles.recallGrid}>{items.map((item, index) => <article className={styles.recallCard} key={item.id} style={{ animationDelay: `${index * 45}ms` }}><div className={styles.recallTop}><span className="mono">MEMORY {String(index + 1).padStart(2, '0')}</span><time dateTime={item.created}>Saved {date(item.created)}</time></div><h2>{item.title}</h2>{item.excerpt && <p className={styles.recallExcerpt}>{item.excerpt}</p>}<div className={styles.recallReasons}><span className={styles.eyebrow}>WHY THIS MEMORY</span><ul>{(item.reasons?.length ? item.reasons : [item.reason]).map(reason => <li key={reason}>{reason}</li>)}</ul></div><div className={styles.actionRow}><button className="button orange" onClick={() => onSource(item.id)}>REVISIT MEMORY <ArrowUpRight size={15} /></button><button className="text-button" disabled={!!busy} onClick={() => dismiss(item.id)}><X size={13} /> {busy === item.id ? 'DISMISSING…' : 'DISMISS'}</button></div></article>)}</div> : <div className="empty"><Bookmark size={42} strokeWidth={1} /><h3>{enabled ? 'LET YOUR KNOWLEDGE GROW.' : 'RECALL IS PAUSED.'}</h3><p>{enabled ? 'Save related memories, add meaningful tags, or set your interests. Useful older ideas will find their way back here.' : 'Turn on memory rediscovery in Settings to see recommendations again.'}</p></div>}
    </section>;
}
