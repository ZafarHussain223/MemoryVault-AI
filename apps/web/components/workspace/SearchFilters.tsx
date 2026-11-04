'use client';
import { Collection } from '@/lib/api';
import { DOCUMENT_FORMATS } from '@/lib/documentFormats';
export type SearchFilterValues = {
    kind: string;
    format: string;
    tag: string;
    collection_id: string;
    date_from: string;
    date_to: string;
};
export const emptyFilters: SearchFilterValues = { kind: '', format: '', tag: '', collection_id: '', date_from: '', date_to: '' };
export default function SearchFilters({ value, onChange, collections }: {
    value: SearchFilterValues;
    onChange: (next: SearchFilterValues) => void;
    collections: Collection[];
}) {
    const update = (key: keyof SearchFilterValues, next: string) => onChange({ ...value, [key]: next });
    return <details className="search-filter-panel"><summary><span>Refine your search</span><span className="mono">{Object.values(value).filter(Boolean).length || 'ALL'} FILTERS</span></summary><div className="search-filter-grid"><label>Source type<select value={value.kind} onChange={e => update('kind', e.target.value)}><option value="">All sources</option><option value="file">Documents</option><option value="note">Notes</option><option value="link">Saved links & transcripts</option></select></label><label>Format<select value={value.format} onChange={e => update('format', e.target.value)}><option value="">All formats</option>{DOCUMENT_FORMATS.map(f => <option key={f} value={f}>{f.toUpperCase()}</option>)}</select></label><label>Collection<select value={value.collection_id} onChange={e => update('collection_id', e.target.value)}><option value="">All collections</option>{collections.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}</select></label><label>Tag<input value={value.tag} onChange={e => update('tag', e.target.value)} maxLength={50} placeholder="research"/></label><label>Saved from<input type="date" value={value.date_from} max={value.date_to || undefined} onChange={e => update('date_from', e.target.value)}/></label><label>Saved through<input type="date" value={value.date_to} min={value.date_from || undefined} onChange={e => update('date_to', e.target.value)}/></label></div><button className="text-button" type="button" onClick={() => onChange({ ...emptyFilters })}>CLEAR FILTERS</button><p className="fine-print">Press Search to apply these filters.</p></details>;
}
