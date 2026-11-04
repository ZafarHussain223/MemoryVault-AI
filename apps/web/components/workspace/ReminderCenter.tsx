'use client';

import { useEffect, useState } from 'react';
import { AlarmClock, ArrowUpRight, CalendarPlus, Check, LoaderCircle, Pencil, Trash2, X } from 'lucide-react';
import { api, post, type Doc } from '@/lib/api';
import styles from './Engagement.module.css';

type Reminder = { id: string; document_id: string | null; title: string; due_at: string; status: 'pending' | 'done'; created: string; notified_at: string | null };
function localInput(value: Date) {
    const pad = (part: number) => String(part).padStart(2, '0');
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}
function localTime(value: string) { return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }); }

export default function ReminderCenter({ documents, onSource, onChanged }: { documents: Doc[]; onSource: (id: string) => void; onChanged: () => void }) {
    const [items, setItems] = useState<Reminder[]>([]), [loaded, setLoaded] = useState(false), [busy, setBusy] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('');
    const [editing, setEditing] = useState<string | null>(null), [title, setTitle] = useState(''), [source, setSource] = useState(''), [due, setDue] = useState('');
    const [timezone, setTimezone] = useState('your device time zone');
    useEffect(() => {
        setDue(localInput(new Date(Date.now() + 24 * 60 * 60 * 1000)));
        setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
        let active = true;
        api<Reminder[]>('/reminders').then(data => { if (active) setItems(data); })
            .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Could not load reminders.'); })
            .finally(() => { if (active) setLoaded(true); });
        return () => { active = false; };
    }, []);
    async function refresh() { setItems(await api<Reminder[]>('/reminders')); onChanged(); }
    function clear() { setEditing(null); setTitle(''); setSource(''); setDue(localInput(new Date(Date.now() + 24 * 60 * 60 * 1000))); }
    async function save(event: React.FormEvent) {
        event.preventDefault();
        const chosen = new Date(due);
        if (!Number.isFinite(chosen.getTime()) || chosen.getTime() <= Date.now()) { setError('Choose a reminder time in the future.'); return; }
        setBusy('form'); setError(''); setNotice('');
        try {
            const body = { title: title.trim(), document_id: source || null, due_at: chosen.toISOString() };
            if (editing) await api('/reminders/' + editing, { method: 'PATCH', body: JSON.stringify(body) });
            else await post('/reminders', body);
            clear(); await refresh(); setNotice(editing ? 'Reminder rescheduled.' : 'Reminder scheduled.');
        } catch (e) { setError(e instanceof Error ? e.message : 'The reminder could not be saved.'); }
        finally { setBusy(''); }
    }
    async function change(item: Reminder, action: 'done' | 'delete') {
        setBusy(item.id); setError(''); setNotice('');
        try {
            await api('/reminders/' + item.id, action === 'delete' ? { method: 'DELETE' } : { method: 'PATCH', body: JSON.stringify({ status: 'done' }) });
            if (editing === item.id) clear();
            await refresh(); setNotice(action === 'done' ? 'Reminder marked done.' : 'Reminder deleted.');
        } catch (e) { setError(e instanceof Error ? e.message : 'Could not update the reminder.'); }
        finally { setBusy(''); }
    }
    const pending = items.filter(item => item.status === 'pending');
    return <section className={styles.reminderCenter} aria-labelledby="reminders-title">
        <div className="section-header"><h2 id="reminders-title"><AlarmClock size={18} /> RETURN TO AN IDEA</h2><span className="mono">{pending.length} SCHEDULED</span></div>
        <p className="muted">A small nudge, at the right time. Due reminders appear here while your vault is open, or when you return.</p>
        <form onSubmit={save} className={styles.reminderForm}>
            <label>Reminder title<input name="reminder_title" value={title} onChange={e => setTitle(e.target.value)} maxLength={160} required disabled={!!busy} placeholder="Revisit those research notes…" /></label>
            <div className={styles.formGrid}>
                <label>Related memory (optional)<select aria-label="Reminder memory" value={source} disabled={!!busy} onChange={e => setSource(e.target.value)}><option value="">No linked memory</option>{documents.map(doc => <option key={doc.id} value={doc.id}>{doc.title}</option>)}{source && !documents.some(doc => doc.id === source) && <option value={source}>Linked memory</option>}</select></label>
                <label>Remind me at<input aria-label="Reminder date and time" type="datetime-local" value={due} onChange={e => setDue(e.target.value)} required disabled={!!busy} /></label>
            </div>
            <p className={styles.caption}>Time zone: {timezone}. Reminders can be scheduled up to one year ahead.</p>
            <div className={styles.actionRow}><button className="button orange" disabled={!!busy}>{busy === 'form' ? <LoaderCircle className="spin" size={15} /> : <CalendarPlus size={15} />}{editing ? 'RESCHEDULE REMINDER' : 'SCHEDULE REMINDER'}</button>{editing && <button type="button" className="text-button" disabled={!!busy} onClick={clear}><X size={14} /> CANCEL EDIT</button>}</div>
        </form>
        {notice && <p className="success-text" role="status">{notice}</p>}{error && <p className="error" role="alert">{error}</p>}
        {!loaded ? <p className="muted" role="status">Loading reminders…</p> : pending.length ? <div className={styles.reminderList}>{pending.map(item => <article className={styles.reminder} key={item.id}><div className={styles.reminderText}><span className={styles.eyebrow}>{new Date(item.due_at).getTime() <= Date.now() ? 'DUE' : 'UP NEXT'}</span><h3>{item.title}</h3><time dateTime={item.due_at}>{localTime(item.due_at)}</time>{item.document_id && <button className="text-button" onClick={() => onSource(item.document_id!)}>OPEN MEMORY <ArrowUpRight size={13} /></button>}</div><div className={styles.reminderActions}><button className="icon-button" aria-label={'Mark done: ' + item.title} title="Mark done" disabled={!!busy} onClick={() => change(item, 'done')}><Check size={17} /></button><button className="icon-button" aria-label={'Reschedule: ' + item.title} title="Reschedule" disabled={!!busy} onClick={() => { setEditing(item.id); setTitle(item.title); setSource(item.document_id || ''); setDue(localInput(new Date(item.due_at))); setNotice(''); }}><Pencil size={15} /></button><button className="icon-button" aria-label={'Delete reminder: ' + item.title} title="Delete reminder" disabled={!!busy} onClick={() => change(item, 'delete')}><Trash2 size={15} /></button></div></article>)}</div> : <div className={styles.quiet}><AlarmClock size={23} /><p>No upcoming reminders. Give a useful idea a date to come back to.</p></div>}
        {items.some(item => item.status === 'done') && <details className={styles.completed}><summary>Completed reminders ({items.filter(item => item.status === 'done').length})</summary>{items.filter(item => item.status === 'done').map(item => <div className={styles.completedRow} key={item.id}><span><Check size={14} /> {item.title}</span><button className="icon-button" aria-label={'Delete completed reminder: ' + item.title} disabled={!!busy} onClick={() => change(item, 'delete')}><Trash2 size={14} /></button></div>)}</details>}
    </section>;
}
