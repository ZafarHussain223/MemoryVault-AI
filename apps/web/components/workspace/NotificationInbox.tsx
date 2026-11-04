'use client';

import { useState } from 'react';
import { ArrowUpRight, CheckCheck, Mail, Trash2 } from 'lucide-react';
import { api, post } from '@/lib/api';
import styles from './Engagement.module.css';

export type VaultNotification = { id: string; text: string; read: boolean; created: string; kind?: string; document_id?: string | null; reminder_id?: string | null };
export default function NotificationInbox({ items, onChanged, onSource }: { items: VaultNotification[]; onChanged: () => Promise<void>; onSource: (id: string) => void }) {
    const [busy, setBusy] = useState(''), [error, setError] = useState('');
    async function change(id: string, action: 'read' | 'unread' | 'delete') {
        setBusy(id); setError('');
        try {
            if (id === 'all') await post('/notifications/read');
            else await api('/notifications/' + id, action === 'delete' ? { method: 'DELETE' } : { method: 'PATCH', body: JSON.stringify({ read: action === 'read' }) });
            await onChanged();
        } catch (e) { setError(e instanceof Error ? e.message : 'Could not update notifications.'); }
        finally { setBusy(''); }
    }
    return <section aria-labelledby="inbox-title"><div className={styles.inboxHeader}><h2 id="inbox-title">YOUR INBOX</h2><button className="text-button" disabled={!!busy || !items.some(item => !item.read)} onClick={() => change('all', 'read')}><CheckCheck size={14} /> MARK ALL AS READ</button></div>
        {error && <p className="error" role="alert">{error}</p>}
        {items.length ? items.map(item => <article className={styles.inboxItem + (item.read ? ' ' + styles.inboxRead : '')} key={item.id}><div>{!item.read && <span className={styles.unreadLabel}>UNREAD · </span>}<time dateTime={item.created}>{new Date(item.created).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</time><p>{item.text}</p>{item.document_id && <button className="text-button" onClick={() => onSource(item.document_id!)}>OPEN MEMORY <ArrowUpRight size={13} /></button>}</div><div className={styles.inboxActions}><button className="icon-button" aria-label={item.read ? 'Mark notification unread' : 'Mark notification read'} title={item.read ? 'Mark unread' : 'Mark read'} disabled={!!busy} onClick={() => change(item.id, item.read ? 'unread' : 'read')}>{item.read ? <Mail size={15} /> : <CheckCheck size={15} />}</button><button className="icon-button" aria-label="Delete notification" title="Delete notification" disabled={!!busy} onClick={() => change(item.id, 'delete')}><Trash2 size={14} /></button></div></article>) : <div className={styles.quiet}><Mail size={24} /><p>All quiet here. Updates and due reminders appear in this inbox.</p></div>}
    </section>;
}
