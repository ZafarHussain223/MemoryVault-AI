'use client';

import { useEffect, useState } from 'react';
import { Activity, BookOpen, ChartNoAxesCombined, Database, Layers, Network, RotateCcw } from 'lucide-react';
import { api, bytes } from '@/lib/api';
import styles from './Engagement.module.css';

type Day = { date: string; saved: number; searches: number; visits: number; quiz_attempts: number };
type Analytics = {
    days: number; timezone: string; history_enabled: boolean;
    totals: { memories: number; documents: number; notes: number; links: number; storage: number; collections: number; relationships: number };
    activity: Day[];
    study: { sessions: number; cards_reviewed: number; cards_known: number; quiz_attempts: number; quiz_correct: number; quiz_questions: number };
    formats: { format: string; count: number }[];
    topics: { tag: string; count: number; visits: number }[];
};
type Metric = 'saved' | 'searches' | 'visits' | 'quiz_attempts';
const metrics: { key: Metric; title: string }[] = [{ key: 'saved', title: 'Memories saved' }, { key: 'searches', title: 'Searches' }, { key: 'visits', title: 'Memories opened' }, { key: 'quiz_attempts', title: 'Quizzes taken' }];
function shortDate(value: string) { return new Date(value + 'T00:00:00Z').toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' }); }

export default function AnalyticsPanel() {
    const [days, setDays] = useState(30), [metric, setMetric] = useState<Metric>('saved');
    const [data, setData] = useState<Analytics | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(true), [revision, setRevision] = useState(0), [chosenDate, setChosenDate] = useState('');
    useEffect(() => {
        const controller = new AbortController(); setBusy(true); setError('');
        api<Analytics>('/analytics?days=' + days, { signal: controller.signal }).then(value => { setData(value); setChosenDate(''); })
            .catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Analytics could not be loaded.'); })
            .finally(() => { if (!controller.signal.aborted) setBusy(false); });
        return () => controller.abort();
    }, [days, revision]);
    const selected = data?.activity.find(day => day.date === chosenDate) || data?.activity.at(-1);
    const metricTitle = metrics.find(item => item.key === metric)!.title;
    const ceiling = Math.max(1, ...(data?.activity.map(day => day[metric]) || []));
    const totalActivity = data?.activity.reduce((sum, day) => sum + day[metric], 0) || 0;
    return <div className={styles.analytics}>
        <div className="page-heading"><div><span className="mono label">[ A GROWING BODY OF KNOWLEDGE ]</span><h1>SMALL MOMENTS.<br />BIG PICTURE.</h1><p>A real view of what you save, revisit and learn.</p></div><div className={styles.rangePicker} aria-label="Analytics period">{[30, 90].map(value => <button key={value} className={'button compact ' + (days === value ? 'dark' : '')} aria-pressed={days === value} onClick={() => setDays(value)}>{value} DAYS</button>)}</div></div>
        {error && <div className="error" role="alert">{error} <button className="text-button" onClick={() => setRevision(value => value + 1)}><RotateCcw size={14} /> RETRY</button></div>}
        {busy && <p className="muted" role="status">Updating your knowledge picture…</p>}
        {data && <div aria-busy={busy} className={busy ? styles.updating : undefined}>
            <div className="stats">{[{ label: 'MEMORIES', value: data.totals.memories, icon: BookOpen }, { label: 'COLLECTIONS', value: data.totals.collections, icon: Layers }, { label: 'SAVED CONNECTIONS', value: data.totals.relationships, icon: Network }, { label: 'PRIVATE STORAGE', value: bytes(data.totals.storage), icon: Database }].map(({ label, value, icon: Icon }) => <div className="stat" key={label}><span className="mono"><Icon size={13} /> {label}</span><strong>{value}</strong></div>)}</div>
            <section className={'panel ' + styles.activityPanel} aria-labelledby="activity-heading">
                <div className="section-header"><h2 id="activity-heading"><Activity size={18} /> YOUR DAILY RHYTHM</h2><span className={styles.caption}>DAILY TOTALS · {data.timezone}</span></div>
                <div className={styles.metricPicker} aria-label="Activity measure">{metrics.map(item => <button key={item.key} aria-pressed={metric === item.key} className={metric === item.key ? styles.activeMetric : ''} onClick={() => setMetric(item.key)}>{item.title}</button>)}</div>
                <div className={styles.chartSummary}><div><strong>{totalActivity}</strong><span>{metricTitle.toLowerCase()} over {data.days} days</span></div><p aria-live="polite">{selected && <><time dateTime={selected.date}>{shortDate(selected.date)}</time><b>{selected[metric]} {metricTitle.toLowerCase()}</b></>}</p></div>
                <div className={styles.activityChart} role="group" aria-label={metricTitle + ' by day. Select a day for its total.'}>
                    {data.activity.map(day => <button key={day.date} className={selected?.date === day.date ? styles.selectedDay : ''} aria-label={`${shortDate(day.date)}: ${day[metric]} ${metricTitle.toLowerCase()}`} aria-pressed={selected?.date === day.date} title={`${shortDate(day.date)}: ${day[metric]}`} onClick={() => setChosenDate(day.date)}><span style={{ height: `${Math.max(day[metric] ? 3 : 0, day[metric] / ceiling * 100)}%` }} /></button>)}
                </div><div className={styles.chartAxis}><span>{data.activity[0] && shortDate(data.activity[0].date)}</span><span>{data.activity.at(-1) && shortDate(data.activity.at(-1)!.date)}</span></div>
                {!data.history_enabled && <p className={styles.caption}>Search and open history is disabled. Those activity totals include only any records saved before you disabled it.</p>}
                {!totalActivity && <p className={styles.caption}>No recorded {metricTitle.toLowerCase()} in this period. Your next action can be the first data point.</p>}
                <details className={styles.dataTable}><summary>View daily totals as a table</summary><div><table><caption>Saved activity over the last {data.days} days ({data.timezone})</caption><thead><tr><th scope="col">Date</th>{metrics.map(item => <th key={item.key} scope="col">{item.title}</th>)}</tr></thead><tbody>{data.activity.map(day => <tr key={day.date}><th scope="row">{day.date}</th>{metrics.map(item => <td key={item.key}>{day[item.key]}</td>)}</tr>)}</tbody></table></div></details>
            </section>
            <div className={styles.analyticsGrid}>
                <section className="panel"><div className="section-header"><h2>WHAT YOU KEEP</h2><ChartNoAxesCombined size={17} /></div><div className={styles.typeCounts}><span><b>{data.totals.notes}</b> notes</span><span><b>{data.totals.documents}</b> documents</span><span><b>{data.totals.links}</b> links</span></div>{data.formats.length ? <ul className={styles.formatList}>{data.formats.map(format => <li key={format.format}><span className="mono">{format.format.toUpperCase()}</span><div><i style={{ width: `${format.count / Math.max(1, data.totals.memories) * 100}%` }} /></div><strong>{format.count}</strong></li>)}</ul> : <p className="muted">File formats appear as you add memories.</p>}</section>
                <section className="panel"><div className="section-header"><h2>SUBJECTS TAKING SHAPE</h2><Network size={17} /></div><p className={styles.caption}>Your most-used tags, counted from saved memories.</p>{data.topics.length ? <ul className={styles.topicList}>{data.topics.map(topic => <li key={topic.tag}><span>{topic.tag}</span><small>{topic.count} {topic.count === 1 ? 'memory' : 'memories'} · {topic.visits} opens</small></li>)}</ul> : <p className="muted">Tag your memories to see the subjects you return to.</p>}</section>
            </div>
            <section className={'panel ' + styles.studyOverview}><div className="section-header"><h2><BookOpen size={18} /> FROM SAVING TO KNOWING</h2><span className={styles.caption}>SAVED STUDY PROGRESS</span></div><div className={styles.studyMetrics}><div><strong>{data.study.sessions}</strong><span>Flashcard sessions</span></div><div><strong>{data.study.cards_reviewed}</strong><span>Cards reviewed</span></div><div><strong>{data.study.cards_known}</strong><span>Marked known</span></div><div><strong>{data.study.quiz_attempts}</strong><span>Quiz attempts</span></div></div>{data.study.quiz_questions > 0 ? <p className="muted">Your saved quiz attempts contain <strong>{data.study.quiz_correct} correct answers out of {data.study.quiz_questions}</strong> questions.</p> : <p className="muted">Complete a source-backed quiz in the Study room to begin tracking your answers.</p>}</section>
        </div>}
    </div>;
}
