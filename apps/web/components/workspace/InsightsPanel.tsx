'use client';
import { useEffect, useState } from 'react';
import Markdown from './SafeMarkdown';
import { ArrowUpRight, Check, LoaderCircle, Sparkles, Tags } from 'lucide-react';
import { api, post, Doc, Source, date } from '@/lib/api';
type Insight = {
    id: string;
    document_id: string;
    document_version: number;
    summary: string;
    detailed_summary: string;
    key_points: string[];
    categories: string[];
    entities: {
        name: string;
        type: string;
    }[];
    citations: Source[];
    created: string;
    model: string;
    stale: boolean;
    coverage?: string;
};
export default function InsightsPanel({ document, generation, onUpdated, onSource }: {
    document: Doc;
    generation: boolean;
    onUpdated: () => Promise<void>;
    onSource: (id: string) => void;
}) {
    const [insight, setInsight] = useState<Insight | null>(null), [loading, setLoading] = useState(true), [busy, setBusy] = useState(''), [error, setError] = useState(''), [applied, setApplied] = useState(false);
    useEffect(() => { let active = true; setLoading(true); setError(''); setApplied(false); api<{
        insight: Insight | null;
    }>('/documents/' + document.id + '/insights').then(r => { if (active)
        setInsight(r.insight); }).catch(e => { if (active)
        setError(e.message); }).finally(() => { if (active)
        setLoading(false); }); return () => { active = false; }; }, [document.id, document.version]);
    async function generate() { setBusy('generate'); setError(''); try {
        const r = await post<{
            insight: Insight;
        }>('/documents/' + document.id + '/insights');
        setInsight(r.insight);
        setApplied(false);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : 'Insights could not be generated.');
    }
    finally {
        setBusy('');
    } }
    return <section className="insights-panel"><div className="section-header"><h3><Sparkles size={16}/> SOURCE INSIGHTS</h3><span className="mono">AI INTERPRETATION</span></div>{loading ? <p className="muted"><LoaderCircle size={16} className="spin"/> Reading saved insights…</p> : insight ? <><div className="insight-meta mono"><span>GENERATED {date(insight.created)}</span>{insight.stale && <span className="status pending">SOURCE UPDATED</span>}</div>{insight.stale && <p className="info">This source has changed since these insights were generated. Regenerate before relying on them.</p>}{insight.coverage && <p className="fine-print">{insight.coverage}</p>}<div className="insight-summary"><Markdown>{insight.summary}</Markdown></div>{insight.key_points.length > 0 && <ul className="key-points">{insight.key_points.map((point, i) => <li key={i}>{point}</li>)}</ul>}<details className="insight-details"><summary>Read the detailed summary</summary><Markdown>{insight.detailed_summary}</Markdown></details>{insight.categories.length > 0 && <div className="suggested-tags"><span className="mono">SUGGESTED CATEGORIES</span><div className="tags">{insight.categories.map(c => <span key={c}>{c}</span>)}</div><button className="text-button" disabled={!!busy || applied || insight.stale} onClick={async () => { setBusy('tags'); setError(''); try {
        await post('/documents/' + document.id + '/insights/apply-tags');
        await onUpdated();
        setApplied(true);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : 'Categories could not be applied.');
    }
    finally {
        setBusy('');
    } }}>{applied ? <><Check size={14}/> APPLIED</> : <><Tags size={14}/> APPLY AS TAGS</>}</button></div>}{insight.entities.length > 0 && <details className="insight-details"><summary>{insight.entities.length} people, places & concepts</summary><div className="entity-list">{insight.entities.map((e, i) => <span key={i}>{e.name}<small>{e.type}</small></span>)}</div></details>}{insight.citations.length > 0 && <details className="insight-details"><summary>Inspect supporting source passages</summary>{insight.citations.map((c, i) => <button key={c.chunk_id || i} className="source" onClick={() => onSource(c.document_id)}><span className="mono">[{i + 1}] {c.title}{c.page ? ' · PAGE ' + c.page : ''}<ArrowUpRight size={13}/></span><p>{c.text}</p></button>)}</details>}<p className="fine-print">Generated interpretation can be incomplete. Check the original passages before relying on a claim.</p></> : <p className="muted">Turn this memory into a short overview, key ideas, suggested categories, and named concepts.</p>}{!generation && <p className="fine-print">Connect a Gemini, OpenAI-compatible, or Ollama provider on the server to generate insights. Saved insights remain readable.</p>}<button className="button compact" disabled={!generation || document.status !== 'ready' || !!busy} onClick={generate}>{busy === 'generate' ? <><LoaderCircle size={15} className="spin"/> READING YOUR SOURCE…</> : <><Sparkles size={15}/>{insight ? 'REGENERATE INSIGHTS' : 'GENERATE INSIGHTS'}</>}</button>{error && <p className="error" role="alert">{error}</p>}</section>;
}
