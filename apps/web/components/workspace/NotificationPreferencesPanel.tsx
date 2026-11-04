'use client';

import { useEffect, useState } from 'react';
import { BellRing, Check, LoaderCircle, Save } from 'lucide-react';
import { api } from '@/lib/api';
import styles from './Engagement.module.css';

export type NotificationPreferences = { processing: boolean; reminders: boolean; recall: boolean };
const choices: { key: keyof NotificationPreferences; title: string; description: string }[] = [
    { key: 'processing', title: 'Processing updates', description: 'Know when a memory is ready or needs attention.' },
    { key: 'reminders', title: 'Scheduled reminders', description: 'Show due reminders in your notification inbox.' },
    { key: 'recall', title: 'Memory rediscovery', description: 'Show updates about older memories worth revisiting.' },
];

export default function NotificationPreferencesPanel({ onChanged }: { onChanged: () => void }) {
    const [value, setValue] = useState<NotificationPreferences | null>(null);
    const [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false);
    useEffect(() => {
        let active = true;
        api<NotificationPreferences>('/notification-preferences').then(data => { if (active) setValue(data); })
            .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Could not load notification preferences.'); });
        return () => { active = false; };
    }, []);
    async function save(event: React.FormEvent) {
        event.preventDefault();
        if (!value) return;
        setBusy(true); setSaved(false); setError('');
        try {
            setValue(await api<NotificationPreferences>('/notification-preferences', { method: 'PUT', body: JSON.stringify(value) }));
            setSaved(true); onChanged();
        } catch (e) { setError(e instanceof Error ? e.message : 'Preferences could not be saved.'); }
        finally { setBusy(false); }
    }
    return <section className="panel settings-panel" aria-labelledby="notification-preferences-title">
        <div className="section-header"><h2 id="notification-preferences-title"><BellRing size={18} /> NOTIFICATIONS</h2></div>
        <p className="muted">Choose what appears inside your vault. Reminders are checked when the app is open; email and device push are not enabled.</p>
        {value ? <form onSubmit={save}>
            {choices.map(choice => <label key={choice.key} className="checkbox"><input type="checkbox" checked={value[choice.key]} disabled={busy} onChange={e => { setValue({ ...value, [choice.key]: e.target.checked }); setSaved(false); }} /><span>{choice.title}<small>{choice.description}</small></span></label>)}
            <div className={styles.actionRow}><button className="button" disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}{busy ? 'SAVING…' : 'SAVE NOTIFICATION PREFERENCES'}</button>{saved && <span className={styles.saved} role="status"><Check size={15} /> Saved</span>}</div>
        </form> : !error && <p className="muted" role="status">Loading preferences…</p>}
        {error && <p className="error" role="alert">{error}</p>}
    </section>;
}
