'use client';
import { useEffect, useState } from 'react';
import { KeyRound, Monitor, ShieldCheck, LoaderCircle } from 'lucide-react';
import { api, post } from '@/lib/api';
type Session = {
    id: string;
    expires: number;
    current: boolean;
};
export default function SecurityPanel() {
    const [sessions, setSessions] = useState<Session[]>([]), [loading, setLoading] = useState(true), [busy, setBusy] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('');
    const fail = (e: unknown) => setError(e instanceof Error ? e.message : 'The security action could not be completed.');
    async function refresh() { setSessions(await api<Session[]>('/auth/sessions')); }
    useEffect(() => { let active = true; api<Session[]>('/auth/sessions').then(r => { if (active)
        setSessions(r); }).catch(e => { if (active)
        fail(e); }).finally(() => { if (active)
        setLoading(false); }); return () => { active = false; }; }, []);
    async function revoke(id: string) { setBusy(id); setError(''); try {
        const r = await api<{
            current: boolean;
        }>('/auth/sessions/' + id, { method: 'DELETE' });
        if (r.current) {
            window.location.href = '/login';
            return;
        }
        await refresh();
        setNotice('Session signed out.');
    }
    catch (e) {
        fail(e);
    }
    finally {
        setBusy('');
    } }
    async function change(event: React.FormEvent<HTMLFormElement>) { event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); if (data.get('password') !== data.get('confirmation')) {
        setError('Your new passwords do not match.');
        return;
    } setBusy('password'); setError(''); try {
        await post('/auth/change-password', { current_password: data.get('current_password'), password: data.get('password') });
        form.reset();
        window.location.href = '/login?password=changed';
    }
    catch (e) {
        fail(e);
    }
    finally {
        setBusy('');
    } }
    return <div className="security-grid"><section className="panel settings-panel"><div className="section-header"><h2><KeyRound size={18}/> PASSWORD</h2><ShieldCheck size={18}/></div><p className="muted">Changing your password signs out every session. You will sign in again with your new password.</p><form onSubmit={change}><label>Current password<input type="password" name="current_password" autoComplete="current-password" required maxLength={128}/></label><label>New password<input type="password" name="password" autoComplete="new-password" minLength={10} maxLength={128} required/></label><label>Confirm new password<input type="password" name="confirmation" autoComplete="new-password" minLength={10} maxLength={128} required/></label><button className="button" disabled={!!busy}>{busy === 'password' ? 'UPDATING…' : 'UPDATE PASSWORD'}<KeyRound size={15}/></button></form></section><section className="panel settings-panel"><div className="section-header"><h2>ACTIVE SESSIONS</h2><Monitor size={18}/></div><p className="muted">Manage the sign-ins that can access your private vault.</p>{loading ? <p className="muted"><LoaderCircle className="spin" size={16}/> Loading sessions…</p> : sessions.map(s => <div className="session-row" key={s.id}><Monitor size={18}/><div><strong>{s.current ? 'This session' : 'Another signed-in session'}</strong><small>Expires {new Date(s.expires * 1000).toLocaleString()}</small></div><button className="text-button" disabled={!!busy} onClick={() => revoke(s.id)}>{busy === s.id ? '…' : 'SIGN OUT'}</button></div>)}{sessions.some(s => !s.current) && <button className="button" disabled={!!busy} onClick={async () => { setBusy('others'); setError(''); try {
        await post('/auth/sessions/revoke-others');
        await refresh();
        setNotice('All other sessions signed out.');
    }
    catch (e) {
        fail(e);
    }
    finally {
        setBusy('');
    } }}>SIGN OUT OTHER SESSIONS</button>}<p className="fine-print">Session entries identify active sign-ins; device names and locations are not inferred.</p>{notice && <p className="success-text" role="status">{notice}</p>}</section>{error && <p className="error security-error" role="alert">{error}</p>}</div>;
}
