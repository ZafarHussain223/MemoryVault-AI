'use client';
import { useEffect, useState } from 'react';
import { ArrowUpRight, Check, GitCompareArrows, LoaderCircle, X } from 'lucide-react';
import { api, post, Doc, Source } from '@/lib/api';
type Finding = {
    id: string;
    document_a: string;
    document_b: string;
    explanation: string;
    evidence_a: Source & {
        quote: string;
    };
    evidence_b: Source & {
        quote: string;
    };
    status: string;
    created: string;
    stale: boolean;
};
export default function ContradictionReview({ documents, generation, onSource }: {
    documents: Doc[];
    generation: boolean;
    onSource: (id: string) => void;
}) {
    const [items, setItems] = useState<Finding[]>([]), [chosen, setChosen] = useState<string[]>([]), [busy, setBusy] = useState(''), [error, setError] = useState(''), [disclaimer, setDisclaimer] = useState('Potential contradictions are AI interpretations. Differences in context or time may explain them.'), [showResolved, setShowResolved] = useState(false);
    useEffect(() => { let active = true; api<{
        items: Finding[];
        disclaimer: string;
    }>('/contradictions').then(r => { if (active) {
        setItems(r.items);
        setDisclaimer(r.disclaimer);
    } }).catch(e => { if (active)
        setError(e.message); }); return () => { active = false; }; }, []);
    async function compare() { setBusy('compare'); setError(''); try {
        const r = await post<{
            items: Finding[];
            disclaimer: string;
        }>('/contradictions', { document_ids: chosen });
        setItems(r.items);
        setDisclaimer(r.disclaimer);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : 'These sources could not be compared.');
    }
    finally {
        setBusy('');
    } }
    async function resolve(id: string, status: 'reviewed' | 'dismissed') { setBusy(id); setError(''); try {
        await api('/contradictions/' + id, { method: 'PATCH', body: JSON.stringify({ status }) });
        setItems(xs => xs.map(x => x.id === id ? { ...x, status } : x));
    }
    catch (e) {
        setError(e instanceof Error ? e.message : 'Review could not be saved.');
    }
    finally {
        setBusy('');
    } }
    const visible = items.filter(x => showResolved || !['dismissed', 'reviewed'].includes(x.status));
    return <section className="contradiction-review"><div className="section-header"><h2><GitCompareArrows size={19}/> A SECOND LOOK</h2><span className="mono">COMPARE YOUR SOURCES</span></div><p className="muted">Find claims that may disagree. Choose two to four ready memories and review their evidence side by side.</p><details className="comparison-picker"><summary>{chosen.length ? `${chosen.length} memories selected` : 'Choose memories to compare'}</summary><div className="comparison-options">{documents.filter(d => d.status === 'ready').map(d => <label className="checkbox" key={d.id}><input type="checkbox" checked={chosen.includes(d.id)} disabled={chosen.length >= 4 && !chosen.includes(d.id)} onChange={e => setChosen(ids => e.target.checked ? [...ids, d.id] : ids.filter(id => id !== d.id))}/>{d.title}</label>)}</div></details><button className="button" onClick={compare} disabled={!generation || chosen.length < 2 || !!busy}>{busy === 'compare' ? <><LoaderCircle size={15} className="spin"/> COMPARING SOURCES…</> : <><GitCompareArrows size={15}/> LOOK FOR DIFFERENCES</>}</button>{!generation && <p className="fine-print">Source comparison needs a configured generative AI provider.</p>}<p className="fine-print">{disclaimer}</p>{error && <p className="error" role="alert">{error}</p>}<label className="checkbox"><input type="checkbox" checked={showResolved} onChange={e => setShowResolved(e.target.checked)}/> Show reviewed and dismissed findings</label>{visible.map(f => <article className="comparison-finding" key={f.id}><div className="section-header"><span className="mono">POTENTIAL DISAGREEMENT</span><span className="status">{f.stale ? 'SOURCE UPDATED' : f.status}</span></div><p>{f.explanation}</p>{f.stale && <p className="info">A source changed. Run a new comparison before relying on this finding.</p>}<div className="evidence-pair">{[f.evidence_a, f.evidence_b].map((e, i) => <blockquote key={i}><span className="mono">SOURCE {i === 0 ? 'A' : 'B'}</span><p>“{e.quote}”</p><button className="text-button" onClick={() => onSource(e.document_id)}>{e.title}{e.page ? ' · PAGE ' + e.page : ''}<ArrowUpRight size={13}/></button></blockquote>)}</div><div className="button-row"><button className="button compact" disabled={!!busy || f.status === 'reviewed'} onClick={() => resolve(f.id, 'reviewed')}><Check size={14}/> MARK REVIEWED</button><button className="text-button" disabled={!!busy || f.status === 'dismissed'} onClick={() => resolve(f.id, 'dismissed')}><X size={14}/> DISMISS</button></div></article>)}{!visible.length && <p className="muted comparison-empty">No pending findings. A comparison can return no disagreements; it does not prove that every claim is consistent.</p>}</section>;
}
