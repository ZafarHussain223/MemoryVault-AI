export type User = {
    id: string;
    email: string;
    name: string;
    preferences: {
        history?: boolean;
        recall?: boolean;
        onboarded?: boolean;
        email_verified?: boolean;
        interests?: string[];
        use_case?: string;
        theme?: string;
    };
};
export type Doc = {
    id: string;
    title: string;
    kind: string;
    format: string;
    content?: string;
    content_characters?: number;
    word_count?: number;
    indexed_chunks?: number;
    indexed_pages?: number;
    excerpt: string;
    tags: string[];
    status: string;
    error: string;
    size: number;
    version: number;
    created: string;
    updated: string;
    source_url?: string;
    source_type?: string;
};
export type Source = {
    chunk_id: string;
    document_id: string;
    title: string;
    text: string;
    page: number | null;
    score?: number;
    document_version?: number;
    source_url?: string;
    kind: string;
    created?: string;
    format?: string;
};
export type Collection = {
    id: string;
    title: string;
    rule_tag: string;
    count: number;
    document_ids: string[];
};
export type Message = {
    id: string;
    role: string;
    content: string;
    citations: Source[];
};
export type Caps = {
    generation: boolean;
    semantic: boolean;
    provider: string;
    search_mode: string;
    model: string;
};
let csrf = '';
export function setCSRF(value: string) { csrf = value; }
export class APIError extends Error {
    constructor(message: string, public status: number) { super(message); this.name = 'APIError'; }
}
async function responseError(response: Response) { let message = 'The request could not be completed.'; try {
    const error = await response.json();
    message = typeof error.detail === 'string' ? error.detail : Array.isArray(error.detail) ? error.detail.map((item: {
        msg: string;
    }) => item.msg).join('; ') : message;
}
catch { } ; return new APIError(message, response.status); }
export async function api<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers);
    if (!(options.body instanceof FormData))
        headers.set('Content-Type', 'application/json');
    if (options.method && options.method !== 'GET')
        headers.set('X-CSRF-Token', csrf);
    const response = await fetch('/api/v1' + path, { ...options, headers, credentials: 'same-origin' });
    if (!response.ok)
        throw await responseError(response);
    if (response.status === 204)
        return undefined as T;
    return response.json();
}
export const post = <T = unknown>(path: string, body: unknown = {}, options: RequestInit = {}) => api<T>(path, { ...options, method: 'POST', body: JSON.stringify(body) });
export function upload(file: File, onProgress: (n: number) => void, signal?: AbortSignal): Promise<Doc> {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const abort = () => xhr.abort();
        const cleanup = () => signal?.removeEventListener('abort', abort);
        if (signal?.aborted) {
            reject(new DOMException('Upload canceled.', 'AbortError'));
            return;
        }
        xhr.open('POST', '/api/v1/uploads');
        xhr.setRequestHeader('X-CSRF-Token', csrf);
        xhr.upload.onprogress = e => { if (e.lengthComputable)
            onProgress(Math.round(e.loaded / e.total * 100)); };
        xhr.onload = () => { cleanup(); let data; try {
            data = JSON.parse(xhr.responseText);
        }
        catch {
            reject(new Error('Upload failed.'));
            return;
        } if (xhr.status >= 200 && xhr.status < 300)
            resolve(data);
        else
            reject(new Error(typeof data.detail === 'string' ? data.detail : 'Upload failed.')); };
        xhr.onerror = () => { cleanup(); reject(new Error('Network error during upload.')); };
        xhr.onabort = () => { cleanup(); reject(new DOMException('Upload canceled.', 'AbortError')); };
        signal?.addEventListener('abort', abort, { once: true });
        const form = new FormData();
        form.append('file', file);
        xhr.send(form);
    });
}
export const date = (s: string) => new Date(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
export const bytes = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`;
export async function streamChat(body: {
    question: string;
    conversation_id: string | null;
    document_id?: string;
}, callbacks: {
    onSources: (sources: Source[]) => void;
    onToken: (text: string) => void;
}, signal: AbortSignal): Promise<{
    conversation_id: string;
    message: Message;
}> {
    const response = await fetch('/api/v1/chat/stream', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body), signal });
    if (!response.ok)
        throw await responseError(response);
    if (!response.body)
        throw new Error('Streaming is not supported in this browser.');
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let pending = '', done: {
        conversation_id: string;
        message: Message;
    } | null = null;
    function dispatch(block: string) { const lines = block.split('\n'); let event = 'message'; const values: string[] = []; for (const line of lines) {
        if (line.startsWith('event:'))
            event = line.slice(6).trim();
        if (line.startsWith('data:'))
            values.push(line.slice(5).trimStart());
    } if (!values.length)
        return; const value = JSON.parse(values.join('\n')); if (event === 'error')
        throw new APIError(value.message || 'Generation failed. Please retry.', value.status || 502); if (event === 'sources')
        callbacks.onSources(value.sources || []); if (event === 'token')
        callbacks.onToken(value.text || ''); if (event === 'done')
        done = value; }
    try {
        while (true) {
            const { value, done: ended } = await reader.read();
            pending += decoder.decode(value, { stream: !ended }).replace(/\r\n/g, '\n');
            let boundary;
            while ((boundary = pending.indexOf('\n\n')) >= 0) {
                dispatch(pending.slice(0, boundary));
                pending = pending.slice(boundary + 2);
            }
            if (ended)
                break;
        }
        if (pending.trim())
            dispatch(pending);
        if (!done)
            throw new Error('The connection ended before the answer was saved. Please retry.');
        return done;
    }
    finally {
        reader.releaseLock();
    }
}
