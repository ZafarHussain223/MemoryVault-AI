'use client';
import { useRef, useState } from 'react';
import Markdown from './SafeMarkdown';
import { Bold, Code, Heading2, Link, List, Eye, PenLine } from 'lucide-react';
export default function MarkdownEditor({ value, onChange, label = 'Your note', rows = 10 }: {
    value: string;
    onChange: (value: string) => void;
    label?: string;
    rows?: number;
}) {
    const field = useRef<HTMLTextAreaElement>(null), [preview, setPreview] = useState(false);
    function insert(before: string, after = '') { const el = field.current; if (!el)
        return; const start = el.selectionStart, end = el.selectionEnd; onChange(value.slice(0, start) + before + (value.slice(start, end) || 'text') + after + value.slice(end)); requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + before.length, start + before.length + (end - start || 4)); }); }
    const count = value.trim() ? value.trim().split(/\s+/).length : 0;
    return <div className="markdown-editor"><div className="editor-label">{label}</div><div className="editor-toolbar"><div>{[{ icon: Heading2, title: 'Heading', before: '## ' }, { icon: Bold, title: 'Bold', before: '**', after: '**' }, { icon: List, title: 'List item', before: '- ' }, { icon: Code, title: 'Code block', before: '\n```\n', after: '\n```\n' }, { icon: Link, title: 'Link', before: '[', after: '](https://example.com)' }].map(({ icon: Icon, title, before, after }) => <button type="button" className="icon-button" key={title} aria-label={title} title={title} disabled={preview} onClick={() => insert(before, after)}><Icon size={15}/></button>)}</div><button type="button" className="text-button" onClick={() => setPreview(!preview)}>{preview ? <><PenLine size={14}/> EDIT</> : <><Eye size={14}/> PREVIEW</>}</button></div>{preview ? <div className="editor-preview"><Markdown>{value || 'Nothing to preview yet. Start with a thought.'}</Markdown></div> : <textarea ref={field} className="note-editor" aria-label={label} value={value} onChange={e => onChange(e.target.value)} rows={rows} maxLength={200000} placeholder="# A new idea…"/>}<div className="editor-footer mono"><span>MARKDOWN SUPPORTED</span><span>{count} WORD{count === 1 ? '' : 'S'}</span></div></div>;
}
