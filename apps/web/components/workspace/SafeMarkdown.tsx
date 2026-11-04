'use client';
import ReactMarkdown from 'react-markdown';

/** Render saved content without automatically requesting third-party images. */
export default function SafeMarkdown({children}:{children:string}) {
  return <ReactMarkdown components={{
    img: ({alt}) => <span className="markdown-image-placeholder">[Image: {alt || 'embedded image'} — open the original source to view]</span>,
    a: ({href, children}) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
  }}>{children}</ReactMarkdown>;
}
