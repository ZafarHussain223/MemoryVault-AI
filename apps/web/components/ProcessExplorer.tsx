'use client';

import {useId, useState, type KeyboardEvent} from 'react';
import {ArrowUpRight, FileText, Network, Search} from 'lucide-react';
import Link from 'next/link';

const steps = [
  {title: 'CAPTURE', text: 'Drop in a document or write a note. Keep the original, always.', caption: 'A PLACE TO BEGIN', explanation: 'A passing idea. A useful PDF. Your research notes. Bring them together without losing where they came from.', action: 'START YOUR VAULT', href: '/register', icon: FileText},
  {title: 'CONNECT', text: 'Add tags, build collections, and find the subjects they share.', caption: 'THE THREAD BETWEEN IDEAS', explanation: 'Shared tags reveal real relationships in your knowledge graph. Collections keep those relationships useful and easy to revisit.', action: 'EXPLORE THE GRAPH', href: '/app/graph', icon: Network},
  {title: 'RECALL', text: 'Find the passage. Follow the source. Pick up the thought.', caption: 'LESS SEARCHING. MORE THINKING.', explanation: 'Search across saved material. When a generative AI provider is configured, ask questions and open the source passages behind the answer.', action: 'OPEN YOUR WORKSPACE', href: '/app', icon: Search},
];

export default function ProcessExplorer() {
  const [active, setActive] = useState(0);
  const id = useId().replace(/:/g, '');
  const step = steps[active];
  function keys(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (index + 1) % 3;
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (index + 2) % 3;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = 2;
    else return;
    event.preventDefault(); setActive(next);
    document.getElementById(`${id}-step-${next}`)?.focus();
  }
  return <div className="process-explorer" data-motion-scene>
    <div className="steps" role="tablist" aria-label="How MemoryVault works" aria-orientation="vertical">{steps.map((item, index) => <button className={`step ${active === index ? 'step-active' : ''}`} key={item.title} role="tab" id={`${id}-step-${index}`} aria-selected={active === index} aria-controls={`${id}-process-panel`} tabIndex={active === index ? 0 : -1} onClick={() => setActive(index)} onKeyDown={event => keys(event, index)} data-cursor="FOLLOW"><span className="mono">0{index + 1}</span><span><strong>{item.title}</strong><span className="step-description">{item.text}</span></span><ArrowUpRight size={21}/></button>)}</div>
    <div className={`process-visual process-stage-${active}`} role="tabpanel" id={`${id}-process-panel`} aria-labelledby={`${id}-step-${active}`} tabIndex={0}>
      <div className="process-visual-top mono"><span>KNOWLEDGE FLOW / 0{active + 1}</span><step.icon size={18}/></div>
      <svg viewBox="0 0 500 205" role="img" aria-label={active === 0 ? 'Documents gathered into one vault' : active === 1 ? 'Saved documents connected by shared tags' : 'Retrieved passage linked back to its source'}>
        
        <g className="flow-connections" stroke="var(--accent)" fill="none"><path d="M100 103H250M250 103L390 50M250 103L390 155" strokeDasharray="4 5"/><circle cx="250" cy="103" r="48" opacity=".2"/><circle cx="250" cy="103" r="38" opacity=".4"/></g>
        <g className="flow-original" stroke="currentColor" fill="var(--ink)"><path d="M66 64h50l18 18v67H66Z"/><path d="M116 64v18h18M78 99h43M78 112h43M78 125h28" fill="none"/><path d="M59 71v86h68" opacity=".4"/></g>
        <g className="flow-hub" stroke="var(--accent)" fill="var(--ink)"><circle cx="250" cy="103" r="29"/><path d="m236 110 14-20 14 20h-28" fill="none"/><circle cx="236" cy="110" r="3" fill="var(--accent)"/><circle cx="250" cy="90" r="3" fill="var(--accent)"/><circle cx="264" cy="110" r="3" fill="var(--accent)"/></g>
        <g className="flow-result-top" stroke="currentColor" fill="var(--ink)"><rect x="359" y="29" width="66" height="44"/><path d="M370 42h42M370 53h30M370 63h38" opacity=".55"/><rect className="flow-highlight" x="367" y="48" width="49" height="10" fill="var(--accent)" stroke="none" fillOpacity=".3"/></g>
        <g className="flow-result-bottom" stroke="currentColor" fill="var(--ink)"><rect x="359" y="134" width="66" height="44"/><path d="M370 147h42M370 158h30M370 168h38" opacity=".55"/></g>
        <g className="flow-labels" fill="currentColor" fontSize="8" fontFamily="monospace" textAnchor="middle"><text x="100" y="181">ORIGINAL</text><text x="250" y="181">YOUR VAULT</text><text x="393" y="99">CONNECTED SOURCES</text></g>
      </svg>
      <div className="process-explanation" key={active}><span className="mono">{step.caption}</span><p>{step.explanation}</p><Link href={step.href} className="small-link">{step.action}<ArrowUpRight size={15}/></Link></div>
    </div>
  </div>;
}
