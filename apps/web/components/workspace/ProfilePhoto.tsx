'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { Camera, LoaderCircle, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import './profile.css';

type Photo = { present: boolean; version: string | null; url: string | null };
const emptyPhoto: Photo = { present: false, version: null, url: null };
const changedEvent = 'memoryvault-profile-photo-changed';

export default function ProfilePhoto({ name, compact = false }: { name: string; compact?: boolean }) {
    const [photo, setPhoto] = useState<Photo>(emptyPhoto);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const input = useRef<HTMLInputElement>(null);
    const inputId = useId();
    useEffect(() => {
        const controller = new AbortController();
        api<Photo>('/profile/photo/info', { signal: controller.signal }).then(setPhoto).catch((failure: unknown) => {
            if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Your profile photo could not be loaded.');
        }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
        const changed = (event: Event) => { setPhoto((event as CustomEvent<Photo>).detail); setError(''); };
        window.addEventListener(changedEvent, changed);
        return () => { controller.abort(); window.removeEventListener(changedEvent, changed); };
    }, []);
    function publish(value: Photo) {
        setPhoto(value);
        window.dispatchEvent(new CustomEvent<Photo>(changedEvent, { detail: value }));
    }
    async function save(file: File) {
        setError(''); setNotice('');
        if (file.size > 2 * 1024 * 1024) { setError('Choose an image that is 2 MB or smaller.'); return; }
        setBusy(true);
        try {
            const form = new FormData(); form.append('file', file);
            publish(await api<Photo>('/profile/photo', { method: 'PUT', body: form }));
            setNotice('Profile photo saved.');
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : 'Your photo could not be saved. Try again.');
        } finally { setBusy(false); }
    }
    async function remove() {
        setBusy(true); setError(''); setNotice('');
        try {
            publish(await api<Photo>('/profile/photo', { method: 'DELETE' }));
            setNotice('Profile photo removed.');
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : 'Your photo could not be removed. Try again.');
        } finally { setBusy(false); }
    }
    const portrait = <span className={'profile-portrait ' + (compact ? 'profile-portrait-compact' : '')} aria-busy={loading || busy}>
        {/* The authenticated endpoint must be requested directly with the user's cookies. */}
        {photo.present && photo.url ? <img src={photo.url} alt={compact ? '' : `${name || 'Your'} profile photo`} width={96} height={96}
            onError={() => { setPhoto(emptyPhoto); if (!compact) setError('Your photo could not be displayed. Refresh to try again.'); }} /> :
            <span aria-hidden="true">{(name.trim()[0] || 'M').toUpperCase()}</span>}
        {!compact && busy && <span className="portrait-busy"><LoaderCircle size={24} className="spin" /></span>}
    </span>;
    if (compact) return portrait;
    return <section className="panel settings-panel profile-photo-panel" aria-labelledby={inputId + '-heading'}>
        <div className="section-header"><h2 id={inputId + '-heading'}>PROFILE PHOTO</h2><Camera size={19} /></div>
        <div className="profile-photo-editor">{portrait}<div className="profile-photo-controls">
            <p>A familiar face for your private workspace.</p>
            <input ref={input} id={inputId} className="profile-file-input" type="file" accept="image/jpeg,image/png,image/webp"
                aria-label="Choose profile photo" disabled={busy || loading} onChange={event => {
                    const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; if (file) void save(file);
                }} />
            <div className="button-row"><button className="button" type="button" disabled={busy || loading} onClick={() => input.current?.click()}>
                <Camera size={15} />{busy ? 'SAVING…' : photo.present ? 'CHANGE PHOTO' : 'UPLOAD PHOTO'}</button>
                {photo.present && <button className="text-button" type="button" disabled={busy} onClick={() => void remove()}><Trash2 size={14} /> REMOVE PHOTO</button>}
            </div>
            <small className="muted">JPEG, PNG or WebP · up to 2 MB and 8 million pixels. Resized privately; original image metadata is removed.</small>
        </div></div>
        {loading && <p className="muted" role="status">Loading your photo…</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {notice && <p className="success-text" role="status">{notice}</p>}
    </section>;
}
