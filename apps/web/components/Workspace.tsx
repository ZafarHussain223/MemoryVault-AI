'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import Markdown from './workspace/SafeMarkdown';
import { ArrowUpRight, ArrowRight, Plus, Search, LayoutDashboard, FolderOpen, MessagesSquare, Network, Clock, Layers, GraduationCap, RotateCcw, ChartNoAxesCombined, Settings, Bell, LogOut, Upload, FileText, X, Menu, Grid2X2, List, Download, Trash2, Save, Check, ChevronRight, Inbox, LoaderCircle, Pencil, Link as LinkIcon, Square } from 'lucide-react';
import Logo from './Logo';
import ImportMemory from './workspace/ImportMemory';
import SearchFilters, { emptyFilters, SearchFilterValues } from './workspace/SearchFilters';
import SecurityPanel from './workspace/SecurityPanel';
import InsightsPanel from './workspace/InsightsPanel';
import QuizRoom from './workspace/QuizRoom';
import ContradictionReview from './workspace/ContradictionReview';
import MarkdownEditor from './workspace/MarkdownEditor';
import DocumentEditor from './workspace/DocumentEditor';
import DocumentViewer from './workspace/DocumentViewer';
import viewerStyles from './workspace/DocumentViewer.module.css';
import { DOCUMENT_ACCEPT, MAX_UPLOAD_BYTES } from '@/lib/documentFormats';
import RelationshipsPanel from './workspace/RelationshipsPanel';
import ProfilePhoto from './workspace/ProfilePhoto';
import AnalyticsPanel from './workspace/AnalyticsPanel';
import RecallPanel from './workspace/RecallPanel';
import ReminderCenter from './workspace/ReminderCenter';
import NotificationInbox, { type VaultNotification } from './workspace/NotificationInbox';
import NotificationPreferencesPanel from './workspace/NotificationPreferencesPanel';
import { api, post, setCSRF, upload, date, bytes, APIError, streamChat, User, Doc, Source, Collection, Message, Caps } from '@/lib/api';
const links = [['dashboard', 'Overview', LayoutDashboard], ['vault', 'My vault', FolderOpen], ['search', 'AI search', Search], ['chat', 'Ask your vault', MessagesSquare], ['graph', 'Knowledge graph', Network], ['timeline', 'Memory timeline', Clock], ['collections', 'Collections', Layers], ['study', 'Study room', GraduationCap], ['recall', 'Memory recall', RotateCcw], ['analytics', 'Analytics', ChartNoAxesCombined]] as const;
type Dashboard = {
    documents: number;
    notes: number;
    storage: number;
    collections: number;
    recent: Doc[];
    activity: {
        date: string;
        count: number;
    }[];
    events: {
        id: string;
        text: string;
        created: string;
    }[];
    capabilities: Caps;
};
type Graph = {
    nodes: {
        id: string;
        title: string;
        kind: string;
        tags: string[];
    }[];
    edges: {
        id: string;
        source: string;
        target: string;
        label: string;
    }[];
    basis: string;
};
type Study = {
    id: string;
    document_id: string;
    stale?: boolean;
    cards: {
        question: string;
        answer: string;
        citation: Source;
    }[];
    progress: Record<string, boolean>;
};
function Modal({ open, onOpen, title, description, children, wide = false }: {
    open: boolean;
    onOpen: (v: boolean) => void;
    title: string;
    description?: string;
    wide?: boolean;
    children: React.ReactNode;
}) { return <Dialog.Root open={open} onOpenChange={onOpen}><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className={'modal'+(wide?' '+viewerStyles.detailModal:'')}><div className="modal-heading"><Dialog.Title>{title}</Dialog.Title><Dialog.Close className="icon-button" aria-label="Close dialog"><X size={20}/></Dialog.Close></div><Dialog.Description className="muted">{description || 'Manage your personal knowledge.'}</Dialog.Description>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>; }
function Empty({ title, body, action }: {
    title: string;
    body: string;
    action?: React.ReactNode;
}) { return <div className="empty"><Inbox size={42} strokeWidth={1}/><h3>{title}</h3><p>{body}</p>{action}</div>; }
export default function Workspace() {
    const pathname = usePathname();
    const router = useRouter();
    const section = pathname.split('/')[2] || 'dashboard';
    const [user, setUser] = useState<User | null>(null), [caps, setCaps] = useState<Caps | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState(''), [notice, setNotice] = useState(''), [mobile, setMobile] = useState(false);
    const [docs, setDocs] = useState<Doc[]>([]), [total, setTotal] = useState(0), [dashboard, setDashboard] = useState<Dashboard | null>(null), [collections, setCollections] = useState<Collection[]>([]), [notifications, setNotifications] = useState<VaultNotification[]>([]), [graph, setGraph] = useState<Graph | null>(null);
    const [query, setQuery] = useState(''), [filter, setFilter] = useState(''), [sort, setSort] = useState('newest'), [view, setView] = useState('grid'), [collectionFilter, setCollectionFilter] = useState('');
    const [searchFilters, setSearchFilters] = useState<SearchFilterValues>({ ...emptyFilters });
    const [captureType, setCaptureType] = useState<'files' | 'link'>('files'), [editingCollection, setEditingCollection] = useState<Collection | null>(null), [renamingConversation, setRenamingConversation] = useState<{
        id: string;
        title: string;
    } | null>(null);
    const uploadController = useRef<AbortController | null>(null), chatController = useRef<AbortController | null>(null), messagesElement = useRef<HTMLDivElement>(null);
    const [searchResults, setSearchResults] = useState<Source[] | null>(null), [searchBusy, setSearchBusy] = useState(false);
    const [editorDirty,setEditorDirty]=useState(false),[editorBusy,setEditorBusy]=useState(false),[membershipPending,setMembershipPending]=useState<Record<string,boolean>>({});
    const [selected, setSelected] = useState<Doc | null>(null), [noteOpen, setNoteOpen] = useState(false), [collectionOpen, setCollectionOpen] = useState(false), [uploadOpen, setUploadOpen] = useState(false), [notificationsOpen, setNotificationsOpen] = useState(false), [commandOpen, setCommandOpen] = useState(false), [onboarding, setOnboarding] = useState(false);
    const [title, setTitle] = useState(''), [content, setContent] = useState(''), [tags, setTags] = useState(''), [saving, setSaving] = useState(false), [progress, setProgress] = useState<number | null>(null), [uploadName, setUploadName] = useState(''), [confirmDelete, setConfirmDelete] = useState(false);
    const [conversationList, setConversationList] = useState<{
        id: string;
        title: string;
    }[]>([]), [conversation, setConversation] = useState<string | null>(null), [messages, setMessages] = useState<Message[]>([]), [question, setQuestion] = useState(''), [chatBusy, setChatBusy] = useState(false);
    const [studies, setStudies] = useState<Study[]>([]), [studyDoc, setStudyDoc] = useState(''), [studyBusy, setStudyBusy] = useState(false), [flipped, setFlipped] = useState<Record<string, boolean>>({});
    const [graphZoom, setGraphZoom] = useState(1), [graphQuery, setGraphQuery] = useState('');
    const fileRef = useRef<HTMLInputElement>(null);
    const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : 'Something went wrong.'), []);
    const load = useCallback(async () => { try {
        const [ds, dash, cs, ns] = await Promise.all([api<{
                items: Doc[];
                total: number;
            }>('/documents?limit=100'), api<Dashboard>('/dashboard'), api<Collection[]>('/collections'), api<VaultNotification[]>('/notifications')]);
        setDocs(ds.items);
        setTotal(ds.total);
        setDashboard(dash);
        setCollections(cs);
        setNotifications(ns);
        setCaps(dash.capabilities);
    }
    catch (e) {
        fail(e);
    } }, [fail]);
    useEffect(() => { api<{
        user: User;
        csrf: string;
        capabilities: Caps;
    }>('/auth/me').then(r => { setCSRF(r.csrf); setUser(r.user); setCaps(r.capabilities); setOnboarding(!r.user.preferences.onboarded); return load(); }).catch(e => { if (e instanceof APIError && e.status === 401)
        router.replace('/login');
    else
        fail(e); }).finally(() => setLoading(false)); }, [load, router]);
    useEffect(() => { const handler = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setCommandOpen(v => !v);
    } }; document.addEventListener('keydown', handler); return () => document.removeEventListener('keydown', handler); }, []);
    useEffect(() => { if (!docs.some(d => ['pending', 'processing'].includes(d.status)))
        return; const id = setInterval(load, 3000); return () => clearInterval(id); }, [docs, load]);
    useEffect(() => { setError(''); setMobile(false); if (!user)
        return; if (section === 'graph')
        api<Graph>('/graph').then(setGraph).catch(fail); if (section === 'chat')
        api<{
            id: string;
            title: string;
        }[]>('/conversations').then(setConversationList).catch(fail); if (section === 'study')
        api<Study[]>('/study').then(setStudies).catch(fail); }, [section, user, fail]);
    const refreshNotifications = useCallback(async () => {
        try { setNotifications(await api<VaultNotification[]>('/notifications')); }
        catch (failure) { fail(failure); }
    }, [fail]);
    useEffect(() => {
        if (!user) return;
        const refresh = () => { if (document.visibilityState === 'visible') void refreshNotifications(); };
        const interval = setInterval(refresh, 30000);
        document.addEventListener('visibilitychange', refresh);
        return () => { clearInterval(interval); document.removeEventListener('visibilitychange', refresh); };
    }, [user, refreshNotifications]);
    useEffect(() => { if (user && notificationsOpen) void refreshNotifications(); }, [user, notificationsOpen, refreshNotifications]);
    useEffect(() => () => { chatController.current?.abort(); }, [section]);
    useEffect(() => { const box = messagesElement.current; if (box && box.scrollHeight - box.scrollTop - box.clientHeight < 180)
        box.scrollTo({ top: box.scrollHeight }); }, [messages, chatBusy]);
    useEffect(() => () => { uploadController.current?.abort(); }, []);
    useEffect(() => { if (!notice)
        return; const id = setTimeout(() => setNotice(''), 4000); return () => clearTimeout(id); }, [notice]);
    async function openDoc(id: string) { if(editorBusy)return;if(selected&&id!==selected.id&&editorDirty&&!confirm('Discard the unsaved draft and open another memory?'))return;try {
        const d = await api<Doc>('/documents/' + id);
        setSelected(d);
        void post('/documents/' + id + '/visit').catch(fail);
        setTitle(d.title);
        setContent(d.content || '');
        setTags(d.tags.join(', '));
        setConfirmDelete(false);
    }
    catch (e) {
        fail(e);
    } }
    function newNote() { setSelected(null); setTitle(''); setContent(''); setTags(''); setNoteOpen(true); }
    async function saveNote(e: React.FormEvent) { e.preventDefault(); setSaving(true); try {
        const body = { title, content, tags: tags.split(',').map(t => t.trim()).filter(Boolean), version: selected?.version };
        if (selected) {
            const d = await api<Doc>('/documents/' + selected.id, { method: 'PATCH', body: JSON.stringify(body) });
            setSelected(d);
        }
        else
            await post('/notes', body);
        setNoteOpen(false);
        setNotice('Saved to your vault.');
        await load();
    }
    catch (e) {
        fail(e);
    }
    finally {
        setSaving(false);
    } }
    async function uploadFiles(files: FileList | null) { if (!files || progress !== null)
        return; setUploadOpen(true); setCaptureType('files'); const controller = new AbortController(); uploadController.current = controller; for (const file of Array.from(files)) {
        if (file.size > MAX_UPLOAD_BYTES) {
            setError(file.name + ' exceeds 100 MB.');
            continue;
        }
        setUploadName(file.name);
        setProgress(0);
        try {
            await upload(file, setProgress, controller.signal);
            setNotice(file.name + ' uploaded. Processing has started.');
        }
        catch (e) {
            if (e instanceof DOMException && e.name === 'AbortError') {
                setNotice('Upload canceled. Files already uploaded remain in your vault.');
                break;
            }
            fail(e);
        }
    } uploadController.current = null; setProgress(null); if (fileRef.current)
        fileRef.current.value = ''; await load(); }
    async function doSearch(e?: React.FormEvent) { e?.preventDefault(); if (!query.trim())
        return; setSearchBusy(true); setError(''); try {
        if (searchFilters.date_from && searchFilters.date_to && searchFilters.date_from > searchFilters.date_to)
            throw new Error('The start date must be before the end date.');
        const params = new URLSearchParams({ q: query, ...searchFilters });
        const r = await api<{
            items: Source[];
        }>('/search?' + params.toString());
        setSearchResults(r.items);
    }
    catch (e) {
        fail(e);
    }
    finally {
        setSearchBusy(false);
    } }
    async function ask(e: React.FormEvent) {
        e.preventDefault();
        if (!question.trim() || chatBusy)
            return;
        const text = question, controller = new AbortController(), userId = 'pending-user-' + Date.now(), assistantId = 'pending-assistant-' + Date.now();
        chatController.current = controller;
        setQuestion('');
        setChatBusy(true);
        setError('');
        setMessages(m => [...m, { id: userId, role: 'user', content: text, citations: [] }, { id: assistantId, role: 'assistant', content: '', citations: [] }]);
        requestAnimationFrame(() => { const box = messagesElement.current; if (box)
            box.scrollTop = box.scrollHeight; });
        try {
            const result = await streamChat({ question: text, conversation_id: conversation }, { onSources: sources => setMessages(ms => ms.map(m => m.id === assistantId ? { ...m, citations: sources } : m)), onToken: token => setMessages(ms => ms.map(m => m.id === assistantId ? { ...m, content: m.content + token } : m)) }, controller.signal);
            setConversation(result.conversation_id);
            setMessages(await api<Message[]>('/conversations/' + result.conversation_id));
            setConversationList(await api('/conversations'));
        }
        catch (e) {
            setMessages(m => m.filter(x => x.id !== userId && x.id !== assistantId));
            setQuestion(text);
            if (e instanceof DOMException && e.name === 'AbortError') {
                setNotice('Generation stopped. Reload the conversation if it finished at the same moment.');
                if (conversation)
                    try {
                        setMessages(await api('/conversations/' + conversation));
                    }
                    catch { }
                ;
                try {
                    setConversationList(await api('/conversations'));
                }
                catch { }
            }
            else
                fail(e);
        }
        finally {
            chatController.current = null;
            setChatBusy(false);
        }
    }
    async function regenerate() { if (!conversation || chatBusy)
        return; const controller = new AbortController(); chatController.current = controller; setChatBusy(true); setError(''); try {
        await post('/conversations/' + conversation + '/regenerate', {}, { signal: controller.signal });
        setMessages(await api('/conversations/' + conversation));
    }
    catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError')
            setNotice('Request canceled. Refresh this conversation to see whether the answer was saved.');
        else
            fail(e);
    }
    finally {
        chatController.current = null;
        setChatBusy(false);
    } }
    async function deleteDoc() { if (!selected)
        return; try {
        await api('/documents/' + selected.id, { method: 'DELETE' });
        setSelected(null);
        setConfirmDelete(false);
        setNotice('Document and its search index deleted.');
        await load();
    }
    catch (e) {
        fail(e);
    } }
    async function savePreferences(values: Record<string, unknown>) { if (!user)
        return; const next = await api<User>('/settings', { method: 'PUT', body: JSON.stringify({ name: user.name, history: true, recall: true, ...user.preferences, ...values }) }); setUser(next); setNotice('Preferences saved.'); return next; }
    const visible = docs.filter(d => (!query || d.title.toLowerCase().includes(query.toLowerCase())) && (!filter || d.kind === filter) && (!collectionFilter || collections.find(c => c.id === collectionFilter)?.document_ids.includes(d.id))).sort((a, b) => sort === 'name' ? a.title.localeCompare(b.title) : b.created.localeCompare(a.created));
    async function updateMembership(collection:Collection,documentId:string,checked:boolean){
      if(membershipPending[collection.id])return;
      setMembershipPending(previous=>({...previous,[collection.id]:true}));
      const update=(ids:string[])=>checked?Array.from(new Set([...ids,documentId])):ids.filter(id=>id!==documentId);
      setCollections(previous=>previous.map(item=>item.id===collection.id?{...item,document_ids:update(item.document_ids),count:update(item.document_ids).length}:item));
      try{await api('/collections/'+collection.id+'/items/'+documentId,{method:checked?'PUT':'DELETE'});setNotice(checked?'Added to '+collection.title+'.':'Removed from '+collection.title+'.')}
      catch(reason){setCollections(previous=>previous.map(item=>item.id===collection.id?collection:item));fail(reason)}
      finally{setMembershipPending(previous=>{const next={...previous};delete next[collection.id];return next})}
    }
    function sourceList(sources: Source[]) { return <div className="sources">{sources.map((s, i) => <button className="source" key={s.chunk_id || i} onClick={() => openDoc(s.document_id)}><span className="mono">[{i + 1}] {s.title}{s.page ? ` · PAGE ${s.page}` : ''} <ArrowUpRight size={13}/></span><p>{s.text}</p></button>)}</div>; }
    function docCards(items: Doc[]) { return <div className={'documents ' + view}>{items.map(d => <button className="document-card" key={d.id} onClick={() => openDoc(d.id)}><div className="document-top"><span className={'file-icon ' + (d.kind === 'note' ? 'note' : '')}><FileText size={23} strokeWidth={1.3}/></span><span className={'status ' + d.status}>{d.status}</span></div><h3>{d.title}</h3><p>{d.excerpt || (d.status === 'ready' ? 'No text content.' : 'Your source is being prepared.')}</p><div className="tags">{d.tags.slice(0, 3).map(t => <span key={t}>{t}</span>)}</div><div className="document-bottom mono"><span>{d.format.toUpperCase()} · {bytes(d.size)}</span><span>{date(d.created)}</span><ArrowUpRight size={14}/></div></button>)}</div>; }
    if (loading || !user)
        return <div className="app-loading"><Logo />{error ? <><p className="error" role="alert">{error}</p><button className="button" onClick={() => window.location.reload()}>TRY AGAIN</button><Link href="/login" className="text-button">SIGN IN</Link></> : <><LoaderCircle className="spin"/><p>Opening your vault…</p></>}</div>;
    const sectionTitle = links.find(l => l[0] === section)?.[1] || 'Settings';
    return <div className={'workspace ' + (user.preferences.theme === 'dark' ? 'dark-theme' : '')}><aside className={'sidebar ' + (mobile ? 'open' : '')}><Logo /><div className="workspace-label mono"><span className="status-dot"/> PERSONAL WORKSPACE</div><button className="sidebar-search" onClick={() => setCommandOpen(true)}><Search size={15}/> Find anything <kbd>Ctrl K</kbd></button><span className="nav-label mono">YOUR KNOWLEDGE</span><nav>{links.map(([path, label, Icon]) => <Link key={path} href={'/app/' + path} className={section === path ? 'active' : ''}><Icon size={17}/>{label}{path === 'vault' && <span className="count">{total}</span>}</Link>)}</nav><div className="sidebar-bottom"><Link href="/app/settings" className={section === 'settings' ? 'active' : ''}><Settings size={17}/> Settings</Link><div className="storage-meter"><div className="mono"><span>VAULT STORAGE</span><span>{bytes(dashboard?.storage || 0)} / 500 MB</span></div><div className="meter"><i style={{ width: Math.min(100, (dashboard?.storage || 0) / 5242880) + '%' }}/></div></div><button className="profile" onClick={() => router.push('/app/settings')}><ProfilePhoto name={user.name || user.email} compact /><span><strong>{user.name || 'Your account'}</strong><small>{user.email}</small></span><ChevronRight size={15}/></button></div></aside>
 <div className="workspace-main"><header className="topbar"><button className="icon-button mobile-menu" aria-label="Toggle navigation" onClick={() => setMobile(!mobile)}><Menu /></button><div className="breadcrumb">WORKSPACE <span>/</span> <strong>{sectionTitle.toUpperCase()}</strong></div><div className="top-actions"><span className="mono local-badge"><i /> PRIVATE VAULT</span><button className="icon-button notification-button" aria-label="Notifications" onClick={() => setNotificationsOpen(true)}><Bell size={19}/>{notifications.some(n => !n.read) && <i />}</button><button className="button dark compact" onClick={() => setUploadOpen(true)}><Plus size={15}/> ADD MEMORY</button></div></header>
 <main key={section} className="workspace-content" data-section={section}>{error && <div className="error banner" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}{notice && <div className="notice" role="status"><Check size={16}/>{notice}</div>}
 {section === 'dashboard' && <><div className="page-heading"><div><span className="mono label">[ YOUR SECOND BRAIN, AT A GLANCE ]</span><h1>GOOD TO HAVE<br />YOU BACK{user.name ? ', ' + user.name.toUpperCase() : ''}.</h1><p>A little less scattered. A lot more connected.</p></div><span className="page-date mono">{new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).toUpperCase()}</span></div><form className="large-search" onSubmit={e => { e.preventDefault(); router.push('/app/search'); doSearch(); }}><Search size={22}/><input aria-label="Search your knowledge" placeholder="What’s on your mind? Search your knowledge…" value={query} onChange={e => setQuery(e.target.value)}/><button className="orange icon-button" aria-label="Search"><ArrowUpRight /></button></form><div className="stats">{[['DOCUMENTS', dashboard?.documents], ['NOTES', dashboard?.notes], ['COLLECTIONS', dashboard?.collections], ['STORAGE USED', bytes(dashboard?.storage || 0)]].map(([label, value]) => <div className="stat" key={label}><span className="mono">{label}<FileText size={17}/></span><strong>{value}</strong><small>In your private vault</small></div>)}</div><div className="section-header"><h2>RECENT MEMORIES <span className="mono">[ {dashboard?.recent.length || 0} ]</span></h2><Link href="/app/vault">VIEW ALL <ArrowUpRight size={15}/></Link></div>{dashboard?.recent.length ? docCards(dashboard.recent) : <Empty title="EVERY SECOND BRAIN STARTS WITH A THOUGHT." body="Add a document or write your first note. This space will grow with you." action={<div className="button-row"><button className="button orange" onClick={() => setUploadOpen(true)}>UPLOAD A DOCUMENT <Upload size={16}/></button><button className="button" onClick={newNote}>WRITE A NOTE <Plus size={16}/></button></div>}/>}<div className="dashboard-lower"><div className="panel"><div className="section-header"><h2>QUICK CAPTURE</h2><Plus size={18}/></div><button className="action-row" onClick={newNote}><FileText /><span><strong>Catch a thought</strong><small>A blank page, ready for your next idea.</small></span><ArrowUpRight /></button><button className="action-row" onClick={() => router.push('/app/chat')}><MessagesSquare /><span><strong>Ask your vault</strong><small>Find answers in what you already know.</small></span><ArrowUpRight /></button></div><div className="panel"><div className="section-header"><h2>RECENT ACTIVITY</h2><Clock size={17}/></div>{dashboard?.events.length ? dashboard.events.slice(0, 4).map(e => <div className="activity" key={e.id}><span className="status-dot"/><span>{e.text}<small>{date(e.created)}</small></span></div>) : <p className="muted">Your saved memories and processing updates will appear here.</p>}</div></div></>}
 {section === 'vault' && <><div className="page-heading"><div><span className="mono label">[ THE THINGS WORTH KEEPING ]</span><h1>YOUR VAULT.</h1><p>{total} memories. One place.</p></div><button className="button orange" onClick={newNote}><Plus size={17}/> NEW NOTE</button></div><div className="toolbar"><div className="input-icon"><Search size={17}/><input placeholder="Find a memory…" value={query} onChange={e => setQuery(e.target.value)} aria-label="Filter memories"/></div><select aria-label="Memory type" value={filter} onChange={e => setFilter(e.target.value)}><option value="">All types</option><option value="file">Documents</option><option value="note">Notes</option><option value="link">Saved links & transcripts</option></select><select aria-label="Collection filter" value={collectionFilter} onChange={e => setCollectionFilter(e.target.value)}><option value="">All collections</option>{collections.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}</select><select aria-label="Sort memories" value={sort} onChange={e => setSort(e.target.value)}><option value="newest">Newest first</option><option value="name">Name</option></select><button className="icon-button" onClick={() => setView(view === 'grid' ? 'list' : 'grid')} aria-label="Toggle list or grid">{view === 'grid' ? <List size={20}/> : <Grid2X2 size={20}/>}</button></div><div onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); uploadFiles(e.dataTransfer.files); }}>{visible.length ? docCards(visible) : <Empty title={docs.length ? 'NO MATCHING MEMORIES.' : 'A CLEAR SPACE. A FRESH START.'} body="Upload a document, drop files here, or create a note." action={<button className="button orange" onClick={() => setUploadOpen(true)}>ADD YOUR FIRST MEMORY <Plus size={17}/></button>}/>}</div>{docs.length < total && <button className="button" onClick={async () => { try {
        const r = await api<{
            items: Doc[];
        }>('/documents?limit=100&offset=' + docs.length);
        setDocs(d => [...d, ...r.items]);
    }
    catch (e) {
        fail(e);
    } }}>LOAD MORE</button>}</>}
 {section === 'search' && <><div className="page-heading"><div><span className="mono label">[ FIND THE THOUGHT ]</span><h1>IT’S IN HERE.<br />LET’S FIND IT.</h1><p>{caps?.semantic ? 'Search by meaning across your knowledge.' : 'Keyword search is active. Enable the local embedding model for semantic search.'}</p></div><span className="pill mono">{caps?.search_mode.toUpperCase()} SEARCH</span></div><form className="large-search" onSubmit={doSearch}><Search /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="What would you like to find?" aria-label="Search query" required/><button className="button orange" disabled={searchBusy}>{searchBusy ? 'SEARCHING…' : 'SEARCH'}<ArrowRight size={16}/></button></form><SearchFilters value={searchFilters} onChange={setSearchFilters} collections={collections}/>{searchResults === null ? <Empty title="REVISIT WHAT YOU KNOW." body="Search for a topic, phrase, or idea from your documents."/> : searchResults.length ? <><div className="section-header"><h2>{searchResults.length} SOURCE PASSAGES</h2><span className="mono">RANKED BY RELEVANCE</span></div>{sourceList(searchResults)}</> : <Empty title="NO MATCHES YET." body="Try a different phrase or add a document about this topic."/>}</>}
 {section === 'chat' && <><div className="page-heading"><div><span className="mono label">[ A CONVERSATION WITH YOUR KNOWLEDGE ]</span><h1>ASK YOUR VAULT.</h1></div><button className="button" disabled={chatBusy} onClick={() => { setConversation(null); setMessages([]); }}><Plus size={16}/> NEW CHAT</button></div>{!caps?.generation && <div className="info">RETRIEVAL ONLY — No generative AI provider is configured. Matching source passages are shown directly.</div>}<div className="chat-layout"><aside className="conversation-list"><span className="mono label">CONVERSATIONS</span>{conversationList.map(c => <div className="conversation-item" key={c.id}><button disabled={chatBusy} className={conversation === c.id ? 'active' : ''} onClick={async () => { try {
        setMessages(await api('/conversations/' + c.id));
        setConversation(c.id);
    }
    catch (e) {
        fail(e);
    } }}>{c.title}</button><button aria-label={'Rename ' + c.title} className="icon-button" disabled={chatBusy} onClick={() => setRenamingConversation(c)}><Pencil size={13}/></button><button disabled={chatBusy} aria-label="Delete conversation" className="icon-button" onClick={async () => { if (!confirm('Delete this conversation?'))
        return; try {
        await api('/conversations/' + c.id, { method: 'DELETE' });
        setConversationList(l => l.filter(x => x.id !== c.id));
        if (conversation === c.id) {
            setConversation(null);
            setMessages([]);
        }
    }
    catch (e) {
        fail(e);
    } }}><Trash2 size={13}/></button></div>)}</aside><div className="chat-main"><div className="messages" ref={messagesElement} role="log" aria-label="Conversation" aria-relevant="additions">{messages.length ? messages.map(m => <article className={'message ' + m.role} key={m.id}><span className="mono label">{m.role === 'user' ? 'YOU' : 'MEMORYVAULT'}</span><Markdown>{m.content}</Markdown>{m.id.startsWith('pending-assistant-') && !m.content && <span className="muted">Reading your sources…</span>}{m.citations?.length > 0 && sourceList(m.citations)}<button className="text-button" disabled={!m.content || m.id.startsWith('pending-')} onClick={() => navigator.clipboard.writeText(m.content).then(() => setNotice('Copied.')).catch(fail)}>COPY</button></article>) : <Empty title="YOUR SOURCES. A NEW PERSPECTIVE." body="Ask a question about something you’ve saved. Every retrieved passage links back to its source."/>}{chatBusy && <p className="muted"><LoaderCircle className="spin" size={16}/> Finding your sources…</p>}</div><div className="chat-controls">{chatBusy ? <button type="button" className="text-button" onClick={() => chatController.current?.abort()}><Square size={12}/> STOP GENERATION</button> : conversation && messages.length > 0 && messages[messages.length - 1].role === 'assistant' ? <button type="button" className="text-button" onClick={regenerate}><RotateCcw size={13}/> REGENERATE LAST ANSWER</button> : <span className="muted">Answers stay grounded in your own sources.</span>}</div><form onSubmit={ask} className="chat-composer"><textarea aria-label="Ask a question" placeholder="Ask anything about your knowledge…" value={question} onChange={e => setQuestion(e.target.value)} maxLength={4000} rows={2}/><button className="icon-button orange" disabled={chatBusy || !question.trim()} aria-label="Send question"><ArrowUpRight /></button></form></div></div></>}
 {section === 'collections' && <><div className="page-heading"><div><span className="mono label">[ A LITTLE ORDER. A LOT OF CLARITY. ]</span><h1>COLLECTIONS.</h1><p>Bring related ideas into the same room.</p></div><button className="button orange" onClick={() => { setEditingCollection(null); setCollectionOpen(true); }}><Plus size={17}/> NEW COLLECTION</button></div>{collections.length ? <div className="collection-grid">{collections.map((c, i) => <article className="collection-card" key={c.id}><div className="mono">[ {String(i + 1).padStart(2, '0')} ] <Layers size={30} strokeWidth={1}/></div><h2>{c.title}</h2><p>{c.count} memories {c.rule_tag && '· Smart rule: #' + c.rule_tag}</p><div className="button-row"><button className="text-button" onClick={() => { setCollectionFilter(c.id); setQuery(''); router.push('/app/vault'); }}>OPEN COLLECTION ↗</button><button className="icon-button" aria-label={'Rename ' + c.title} onClick={() => { setEditingCollection(c); setCollectionOpen(true); }}><Pencil size={15}/></button><button className="icon-button" aria-label={'Delete ' + c.title} onClick={async () => { if (!confirm('Delete this collection? Its memories will be kept.'))
        return; try {
        await api('/collections/' + c.id, { method: 'DELETE' });
        await load();
    }
    catch (e) {
        fail(e);
    } }}><Trash2 size={15}/></button></div></article>)}</div> : <Empty title="BRING RELATED IDEAS TOGETHER." body="Create a collection for a project, a subject, or something you’re curious about." action={<button className="button orange" onClick={() => { setEditingCollection(null); setCollectionOpen(true); }}>CREATE A COLLECTION <Plus size={17}/></button>}/>}</>}
 {section === 'timeline' && <><div className="page-heading"><div><span className="mono label">[ A RECORD OF YOUR CURIOSITY ]</span><h1>YOUR MEMORY<br />TIMELINE.</h1><p>Organized by the date you saved each memory.</p></div></div>{docs.length ? <div className="timeline">{Object.entries(docs.reduce<Record<string, Doc[]>>((a, d) => { const key = date(d.created); (a[key] ??= []).push(d); return a; }, {})).map(([day, items]) => <section key={day}><h2 className="mono">{day}</h2><div>{items.map(d => <button className="timeline-row" onClick={() => openDoc(d.id)} key={d.id}><FileText size={20}/><span><strong>{d.title}</strong><small>{d.kind.toUpperCase()} · {d.tags.join(', ') || 'Untagged'}</small></span><ArrowUpRight size={18}/></button>)}</div></section>)}</div> : <Empty title="THE STORY STARTS HERE." body="Your saved memories will form a timeline as your vault grows."/>}</>}
 {section === 'graph' && <><div className="page-heading"><div><span className="mono label">[ SEE THE BIGGER PICTURE ]</span><h1>CONNECT THE DOTS.</h1><p>{graph?.basis || 'Explore relationships in your saved knowledge.'}</p></div></div><div className="toolbar"><input aria-label="Find graph node" placeholder="Find a node…" value={graphQuery} onChange={e => setGraphQuery(e.target.value)}/><button className="button" onClick={() => setGraphZoom(z => Math.min(2, z + .2))}>ZOOM +</button><button className="button" onClick={() => setGraphZoom(z => Math.max(.5, z - .2))}>ZOOM −</button><button className="button" onClick={() => setGraphZoom(1)}>FIT</button></div>{graph?.nodes.length ? <div className="graph-panel"><svg viewBox="0 0 1000 650" style={{ width: 100 * graphZoom + '%', minWidth: 500 }} aria-label="Knowledge graph"><defs><pattern id="graphgrid" width="25" height="25" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7" fill="currentColor" opacity=".2"/></pattern></defs><rect width="1000" height="650" fill="url(#graphgrid)"/>{graph.edges.map(edge => { const a = graph.nodes.findIndex(n => n.id === edge.source), b = graph.nodes.findIndex(n => n.id === edge.target); const point = (i: number) => [500 + 330 * Math.cos(i / graph.nodes.length * Math.PI * 2), 325 + 230 * Math.sin(i / graph.nodes.length * Math.PI * 2)]; return <g key={edge.id}><title>{edge.label}</title><line x1={point(a)[0]} y1={point(a)[1]} x2={point(b)[0]} y2={point(b)[1]} stroke="var(--accent)" strokeWidth="1.4" opacity=".5"/></g>; })}{graph.nodes.map((n, i) => { const x = 500 + 330 * Math.cos(i / graph.nodes.length * Math.PI * 2), y = 325 + 230 * Math.sin(i / graph.nodes.length * Math.PI * 2); return <g key={n.id} role="button" tabIndex={0} aria-label={'Open ' + n.title} onClick={() => openDoc(n.id)} onKeyDown={e => { if (e.key === 'Enter')
        openDoc(n.id); }} style={{ cursor: 'pointer', opacity: !graphQuery || n.title.toLowerCase().includes(graphQuery.toLowerCase()) ? 1 : .2 }}><circle cx={x} cy={y} r="29" fill="var(--paper)" stroke="var(--ink)"/><text x={x} y={y + 5} textAnchor="middle" fill="var(--ink)" fontSize="13">{n.kind === 'note' ? 'N' : 'D'}</text><text x={x} y={y + 48} textAnchor="middle" fill="var(--ink)" fontSize="12">{n.title.slice(0, 25)}</text></g>; })}</svg><span className="graph-caption mono">{graph.nodes.length} NODES / {graph.edges.length} CONNECTIONS · UP TO 150 MEMORIES</span></div> : <Empty title="KNOWLEDGE IS BETTER CONNECTED." body="Save memories and give related ones a shared tag to reveal their connections."/>}<RelationshipsPanel documents={docs} onChanged={async()=>setGraph(await api<Graph>('/graph'))} onSource={openDoc}/><ContradictionReview documents={docs} generation={!!caps?.generation} onSource={openDoc}/></>}
 {section === 'recall' && <RecallPanel enabled={user.preferences.recall !== false} onSource={openDoc} />}
 {section === 'study' && <><div className="page-heading"><div><span className="mono label">[ FROM READING TO REMEMBERING ]</span><h1>THE STUDY ROOM.</h1><p>Flashcards grounded in a document you choose.</p></div></div>{!caps?.generation && <div className="info">Study generation needs a configured Gemini, OpenAI-compatible, or Ollama provider. Your saved study cards remain available.</div>}<div className="toolbar"><select aria-label="Study document" value={studyDoc} onChange={e => setStudyDoc(e.target.value)}><option value="">Choose a ready document</option>{docs.filter(d => d.status === 'ready').map(d => <option key={d.id} value={d.id}>{d.title}</option>)}</select><button disabled={!caps?.generation || !studyDoc || studyBusy} className="button orange" onClick={async () => { setStudyBusy(true); try {
        await post('/study/' + studyDoc);
        setStudies(await api('/study'));
    }
    catch (e) {
        fail(e);
    }
    finally {
        setStudyBusy(false);
    } }}>{studyBusy ? 'GENERATING…' : 'CREATE FLASHCARDS'}<Plus size={16}/></button></div>{studies.length ? studies.map(s => <section className="study-session" key={s.id}><div className="section-header"><h2>{docs.find(d => d.id === s.document_id)?.title || 'Study session'}</h2><span className="mono">{Object.values(s.progress).filter(Boolean).length}/{s.cards.length} KNOWN</span></div>{s.stale && <p className="info">This source has changed since these flashcards were created. Generate a fresh set before recording progress.</p>}<div className="study-grid">{s.cards.map((c, i) => <article className="flashcard" key={i}><span className="mono label">CARD {i + 1} / {s.cards.length}</span><button className="flashcard-body" aria-pressed={!!flipped[s.id + i]} onClick={() => setFlipped(f => ({ ...f, [s.id + i]: !f[s.id + i] }))}>{flipped[s.id + i] ? c.answer : c.question}<small>CLICK TO {flipped[s.id + i] ? 'SEE QUESTION' : 'REVEAL ANSWER'}</small></button><button className="text-button" onClick={() => openDoc(c.citation.document_id)}>OPEN SOURCE ↗</button><div className="button-row">{[true, false].map(known => <button className="button compact" aria-pressed={s.progress[String(i)] === known} key={String(known)} disabled={s.stale} onClick={async () => { try {
        await api('/study/' + s.id + '/progress', { method: 'PUT', body: JSON.stringify({ card: i, known }) });
        setStudies(await api('/study'));
    }
    catch (e) {
        fail(e);
    } }}>{known ? 'GOT IT' : 'REVIEW AGAIN'}</button>)}</div></article>)}</div></section>) : <Empty title="MAKE IT STICK." body="Choose a document to turn your source material into flashcards."/>}<QuizRoom documents={docs} generation={!!caps?.generation} onSource={openDoc}/></>}
 {section === 'analytics' && <AnalyticsPanel />}
 {section === 'settings' && <><div className="page-heading"><div><span className="mono label">[ MAKE IT YOURS ]</span><h1>YOUR VAULT.<br />YOUR RULES.</h1></div></div><form className="settings-form" onSubmit={async (e) => { e.preventDefault(); setSaving(true); try {
        const f = new FormData(e.currentTarget);
        await savePreferences({ name: f.get('name'), history: f.get('history') === 'on', recall: f.get('recall') === 'on', theme: f.get('theme'), use_case: f.get('use_case'), interests: String(f.get('interests') || '').split(',').map(value => value.trim()).filter(Boolean) });
    }
    catch (e) {
        fail(e);
    }
    finally {
        setSaving(false);
    } }}><div className="panel"><h2>PROFILE & APPEARANCE</h2><label>Display name<input name="name" defaultValue={user.name} maxLength={100}/></label><label>Email<input value={user.email} readOnly/></label><label>Primary use<select name="use_case" defaultValue={user.preferences.use_case || "Personal knowledge"}><option>Personal knowledge</option><option>Student</option><option>Developer</option><option>Researcher</option><option>Professional</option></select></label><label>Appearance<select name="theme" defaultValue={user.preferences.theme || 'light'}><option value="light">Paper / light</option><option value="dark">Ink / dark</option></select></label></div><div className="panel"><h2>PRIVACY & RECALL</h2><label>Interests, separated by commas<input name="interests" maxLength={1000} defaultValue={(user.preferences.interests || []).join(", ")} placeholder="Design, programming, literature…"/><small className="muted">Up to 20 interests. Matching saved tags help your memories resurface.</small></label><label className="checkbox"><input type="checkbox" name="history" defaultChecked={user.preferences.history !== false}/><span>Save search and open history<small>Record searches and memories you open for activity and recall.</small></span></label><label className="checkbox"><input type="checkbox" name="recall" defaultChecked={user.preferences.recall !== false}/><span>Rediscover older memories<small>Rediscover memories using tags, interests, saved connections and open history.</small></span></label><button type="button" className="text-button" onClick={async () => { try {
        await api('/history', { method: 'DELETE' });
        setNotice('Search and open history cleared.');
    }
    catch (e) {
        fail(e);
    } }}>CLEAR SEARCH AND OPEN HISTORY</button></div><button className="button orange" disabled={saving}><Save size={16}/> {saving ? 'SAVING…' : 'SAVE PREFERENCES'}</button></form><ProfilePhoto name={user.name || user.email} /><NotificationPreferencesPanel onChanged={() => void refreshNotifications()} /><SecurityPanel /><div className="panel settings-panel"><h2>EMAIL VERIFICATION</h2><p>{user.preferences.email_verified ? 'Your email address has been verified.' : 'Verify your address using a one-time email link. Local development emails are saved in the server outbox.'}</p><button disabled={user.preferences.email_verified} className="button" onClick={async () => { try {
        const r = await post<{
            message: string;
        }>("/auth/send-verification");
        setNotice(r.message);
    }
    catch (e) {
        fail(e);
    } }}>SEND VERIFICATION EMAIL</button><h2 style={{ marginTop: 30 }}>AI CAPABILITIES</h2><p>Search: <strong>{caps?.search_mode}</strong> · Generative AI: <strong>{caps?.generation ? caps.provider : 'not configured'}</strong></p><p className="muted">Providers and credentials are configured on the server. API secrets are never sent to this browser.</p></div><div className="panel settings-panel"><h2>YOUR DATA</h2><p>Download your vault archive, including original files, notes, collections, conversations, and study data.</p><div className="button-row"><a className="button" href="/api/v1/export/archive"><Download size={16}/> EXPORT DATA</a><button className="button" onClick={async () => { try {
        await post('/auth/logout');
        window.location.href = '/login';
    }
    catch (e) {
        fail(e);
    } }}><LogOut size={16}/> SIGN OUT</button><button className="text-button danger" onClick={async () => { if (prompt('This permanently deletes your account and all vault data. Type DELETE to confirm.') !== 'DELETE')
        return; try {
        await api('/account', { method: 'DELETE' });
        window.location.href = '/';
    }
    catch (e) {
        fail(e);
    } }}>DELETE ACCOUNT</button></div></div></>}
 </main><footer className="app-footer mono"><span>MEMORYVAULT AI / YOUR KNOWLEDGE, CONNECTED.</span><span>YOUR KNOWLEDGE, CONNECTED. <Plus size={12}/></span></footer></div>
 <Modal open={uploadOpen} onOpen={setUploadOpen} title="ADD A MEMORY" description="Save something worth returning to. Your memories stay in your private vault."><div className="capture-tabs"><button className={captureType === 'files' ? 'active' : ''} onClick={() => setCaptureType('files')} aria-pressed={captureType === 'files'}><Upload size={16}/> UPLOAD FILES</button><button className={captureType === 'link' ? 'active' : ''} onClick={() => setCaptureType('link')} aria-pressed={captureType === 'link'}><LinkIcon size={16}/> SAVE A LINK</button><button onClick={() => { setUploadOpen(false); newNote(); }}><FileText size={16}/> WRITE A NOTE</button></div>{captureType === 'files' ? <><div className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); uploadFiles(e.dataTransfer.files); }}><Upload size={34} strokeWidth={1}/><h3>DROP SOMETHING WORTH KEEPING.</h3><p>PDF &amp; EPUB books · Word &amp; PowerPoint · spreadsheets<br />OpenDocument, text, data files and images. Up to 100 MB per file.</p><input ref={fileRef} type="file" multiple accept={DOCUMENT_ACCEPT} onChange={e => uploadFiles(e.target.files)} aria-label="Choose files" disabled={progress !== null}/></div>{progress !== null && <div className="upload-progress" role="status"><p>{uploadName} · {progress}%</p><progress max={100} value={progress}/><button className="text-button" onClick={() => uploadController.current?.abort()}><Square size={12}/> CANCEL REMAINING UPLOADS</button></div>}<p className="muted">Your complete original file is preserved. Large books are indexed in batches; processing status appears in My vault.</p><details className="fine-print"><summary>Supported file formats</summary><p>PDF, EPUB, DOC, DOCX, PPT, PPTX, XLS, XLSX, ODT, ODS, ODP, RTF, TXT, MD, CSV, TSV, JSON, XML, HTML, YAML, LOG, PNG, JPG and WEBP. Older Office formats use the local document converter.</p></details></> : <ImportMemory onImported={async (document) => { setNotice('Source saved. Processing has started.'); await load(); setUploadOpen(false); await openDoc(document.id); }}/>}{error && <p role="alert" className="error">{error}</p>}</Modal>
 <Modal open={noteOpen} onOpen={open=>{if(!open&&saving)return;if(!open&&(title||content||tags)&&!confirm('Discard this unsaved note?'))return;setNoteOpen(open)}} title="CATCH A THOUGHT" description="Write a Markdown note. Save it to make it searchable."><form onSubmit={saveNote}><label>Title<input value={title} onChange={e => setTitle(e.target.value)} required maxLength={255}/></label><MarkdownEditor value={content} onChange={setContent}/><label>Tags, separated by commas<input value={tags} onChange={e => setTags(e.target.value)} placeholder="research, ideas, project"/></label><button className="button orange" disabled={saving}>{saving ? 'SAVING…' : 'SAVE NOTE'}<Save size={16}/></button>{error && <p role="alert" className="error">{error}</p>}</form></Modal>
 <Modal wide open={!!selected && !noteOpen} onOpen={v => { if(!v&&!editorBusy&&(!editorDirty||confirm('Discard the unsaved changes to this memory?')))setSelected(null); }} title={selected?.title || 'Memory'} description={selected ? `${selected.format.toUpperCase()} · ${bytes(selected.size)} · Saved ${date(selected.created)}` : undefined}>{selected && <><div className="detail-actions"><span className={'status ' + selected.status}>{selected.status}</span><a className="button compact" href={'/api/v1/documents/' + selected.id + '/download'}><Download size={14}/> DOWNLOAD</a>{selected.status === 'failed' && <button className="button compact" onClick={async () => { try {
        await post('/documents/' + selected.id + '/retry');
        setSelected(null);
        await load();
    }
    catch (e) {
        fail(e);
    } }}>RETRY</button>}</div>{selected.source_url && <div className="source-provenance"><span className="mono">SAVED FROM {selected.source_type?.toUpperCase() || 'THE WEB'}</span><a href={selected.source_url} target="_blank" rel="noopener noreferrer">{selected.source_url}<ArrowUpRight size={14}/></a>{selected.source_type === 'youtube' && <p className="fine-print">This memory contains the transcript supplied when it was saved.</p>}</div>}{selected.error && <p className="error">{selected.error}</p>}<DocumentEditor key={'editor-'+selected.id} document={selected} onSaved={doc=>{setSelected(current=>current?.id===doc.id?doc:current);void load()}} onDirtyChange={setEditorDirty} onBusyChange={setEditorBusy}/>{selected.kind!=='note'&&<DocumentViewer key={'viewer-'+selected.id} document={selected}/>}<InsightsPanel document={selected} generation={!!caps?.generation} onUpdated={async () => { await load(); await openDoc(selected.id); }} onSource={openDoc}/><div className="detail-collections"><h3>COLLECTIONS</h3>{collections.filter(c => !c.rule_tag).map(c => <label className="checkbox" key={c.id}><input type="checkbox" checked={c.document_ids.includes(selected.id)} disabled={!!membershipPending[c.id]} onChange={event=>void updateMembership(c,selected.id,event.target.checked)}/>{c.title}</label>)}{!collections.length && <p className="muted">Create a collection to organize this memory.</p>}</div><div className="delete-area">{confirmDelete ? <><p>Delete this memory, original file, search index, and associated study data? This cannot be undone.</p><button className="button danger" onClick={deleteDoc}>PERMANENTLY DELETE</button></> : <button className="text-button danger" onClick={() => setConfirmDelete(true)}><Trash2 size={14}/> DELETE MEMORY</button>}</div>{error && <p role="alert" className="error">{error}</p>}</>}</Modal>
 <Modal open={collectionOpen} onOpen={setCollectionOpen} title={editingCollection ? "EDIT COLLECTION" : "MAKE A COLLECTION"} description="Keep related ideas together. Add an optional tag rule for automatic membership."><form onSubmit={async (e) => { e.preventDefault(); setSaving(true); try {
        const body = Object.fromEntries(new FormData(e.currentTarget));
        if (editingCollection)
            await api('/collections/' + editingCollection.id, { method: 'PATCH', body: JSON.stringify(body) });
        else
            await post('/collections', body);
        setCollectionOpen(false);
        await load();
    }
    catch (e) {
        fail(e);
    }
    finally {
        setSaving(false);
    } }}><label>Name<input key={editingCollection?.id || 'new'} name="title" required maxLength={100} defaultValue={editingCollection?.title || ''} placeholder="A project, a subject, a curiosity…"/></label><label>Smart tag rule (optional)<input key={editingCollection?.id || 'new'} name="rule_tag" maxLength={50} defaultValue={editingCollection?.rule_tag || ''} placeholder="e.g. research"/></label><button className="button orange" disabled={saving}>{editingCollection ? 'SAVE COLLECTION' : 'CREATE COLLECTION'} <Plus size={16}/></button>{error && <p role="alert" className="error">{error}</p>}</form></Modal>
 <Modal open={!!renamingConversation} onOpen={v => { if (!v)
        setRenamingConversation(null); }} title="RENAME CONVERSATION" description="Give this conversation a title that is easy to find."><form onSubmit={async (e) => { e.preventDefault(); if (!renamingConversation)
        return; setSaving(true); try {
        const title = String(new FormData(e.currentTarget).get('title'));
        await api('/conversations/' + renamingConversation.id, { method: 'PATCH', body: JSON.stringify({ title }) });
        setConversationList(await api('/conversations'));
        setRenamingConversation(null);
    }
    catch (e) {
        fail(e);
    }
    finally {
        setSaving(false);
    } }}><label>Title<input name="title" required maxLength={100} defaultValue={renamingConversation?.title}/></label><button className="button orange" disabled={saving}>SAVE TITLE <Check size={15}/></button>{error && <p className="error" role="alert">{error}</p>}</form></Modal>
 <Modal open={notificationsOpen} onOpen={setNotificationsOpen} title="WHAT’S NEW" description="Updates and scheduled reminders from your vault.">
    <NotificationInbox items={notifications} onChanged={refreshNotifications} onSource={id => { setNotificationsOpen(false); void openDoc(id); }} />
    <ReminderCenter documents={docs} onChanged={() => void refreshNotifications()} onSource={id => { setNotificationsOpen(false); void openDoc(id); }} />
 </Modal>
 <Modal open={commandOpen} onOpen={setCommandOpen} title="FIND YOUR WAY" description="Search your vault or jump to a workspace."><form onSubmit={e => { e.preventDefault(); setCommandOpen(false); router.push('/app/search'); doSearch(); }}><input autoFocus aria-label="Command search" placeholder="Search your knowledge…" value={query} onChange={e => setQuery(e.target.value)}/><button className="button orange">SEARCH VAULT <Search size={15}/></button></form><div className="command-links">{links.map(([path, label, Icon]) => <button key={path} onClick={() => { setCommandOpen(false); router.push('/app/' + path); }}><Icon size={17}/>{label}<ArrowUpRight size={14}/></button>)}</div></Modal>
 <Modal open={onboarding} onOpen={setOnboarding} title="YOUR KNOWLEDGE, CONNECTED." description="Let’s make this space yours. You can change these preferences in Settings."><form onSubmit={async (e) => { e.preventDefault(); try {
        const f = new FormData(e.currentTarget);
        await savePreferences({ onboarded: true, use_case: f.get('use_case'), interests: String(f.get('interests')).split(',').map(t => t.trim()).filter(Boolean) });
        setOnboarding(false);
    }
    catch (e) {
        fail(e);
    } }}><label>What brings you here?<select name="use_case"><option>Personal knowledge</option><option>Student</option><option>Developer</option><option>Researcher</option><option>Professional</option></select></label><label>What are you curious about?<input name="interests" placeholder="Design, programming, literature…"/></label><p className="muted">Start by adding a file or a note. Search retrieves passages from your own sources. AI-generated answers are available when a provider is configured.</p><div className="button-row"><button className="button orange">ENTER YOUR VAULT <ArrowRight size={17}/></button><button type="button" className="text-button" onClick={() => setOnboarding(false)}>SKIP FOR NOW</button></div></form></Modal>
 </div>;
}
