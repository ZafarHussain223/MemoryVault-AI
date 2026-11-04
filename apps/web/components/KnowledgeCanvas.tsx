'use client';

import {useEffect, useId, useRef, useState, type KeyboardEvent} from 'react';
import {ArrowUpRight, ArrowLeft, ArrowRight, FileText, Link2, Network, Quote, Search, StickyNote, Sparkles} from 'lucide-react';

const memories = [
  {title: 'Learning notes', type: 'NOTE', topic: 'Learning', icon: StickyNote, excerpt: 'Space your practice. Revisit an idea tomorrow, then again next week.', color: 'peach'},
  {title: 'The art of noticing', type: 'ARTICLE', topic: 'Creativity', icon: Link2, excerpt: 'Keep the detail that changes how you see the next problem.', color: 'lilac'},
  {title: 'Research highlights', type: 'DOCUMENT', topic: 'Learning', icon: FileText, excerpt: 'Connecting new ideas to what you already know makes them easier to recall.', color: 'sage'},
];
const modes = [
  {name: 'Capture', icon: FileText, title: 'Keep the part that matters.', detail: 'A useful paragraph. A quick note. The thought you want to come back to.'},
  {name: 'Connect', icon: Network, title: 'One idea leads to another.', detail: 'Shared tags and connections give separate memories a little more context.'},
  {name: 'Recall', icon: Search, title: 'Pick up where your mind left off.', detail: 'Find the passage you need, with a clear path back to the original.'},
];

/** Clearly labelled product illustration; examples never enter the user's vault. */
export default function KnowledgeCanvas({compact = false}: {compact?: boolean}) {
  const id = useId().replace(/:/g, '');
  const [active, setActive] = useState(0);
  const [selected, setSelected] = useState(0);
  const [sourceOpen, setSourceOpen] = useState(false);
  const insight = useRef<HTMLDivElement>(null);
  const focusInsight = useRef(false);
  useEffect(() => {
    if (focusInsight.current) { insight.current?.focus({preventScroll:true}); focusInsight.current = false; }
  }, [sourceOpen]);
  function revealSource(open: boolean, index?: number) {
    focusInsight.current = true;
    if (index !== undefined) setSelected(index);
    setSourceOpen(open);
  }
  const source = memories[selected];
  const SourceIcon = source.icon;
  function choose(index: number) { setActive(index); if (index > 0) setSelected(0); setSourceOpen(false); }
  function keys(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % 3;
    else if (event.key === 'ArrowLeft') next = (index + 2) % 3;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = 2;
    else return;
    event.preventDefault(); choose(next);
    document.getElementById(`${id}-mode-${next}`)?.focus();
  }
  return <div className={`knowledge-canvas knowledge-mode-${active}${compact ? ' knowledge-compact' : ''}`} data-motion-scene aria-hidden={compact || undefined}>
    <div className="knowledge-caption mono"><span><span className="thought-dot"/> A FEW THOUGHTS. A BIGGER PICTURE.</span><span>INTERACTIVE PRODUCT EXAMPLE</span></div>
    <div className="knowledge-modes" role="tablist" aria-label="Explore your connected knowledge">{modes.map((mode,index) => <button key={mode.name} id={`${id}-mode-${index}`} role="tab" aria-selected={active === index} aria-controls={`${id}-mode-panel`} tabIndex={active === index ? 0 : -1} onClick={() => choose(index)} onKeyDown={event => keys(event,index)} data-cursor={mode.name.toUpperCase()}><span className="mono">0{index+1}</span><mode.icon size={17}/>{mode.name}<ArrowRight size={15}/></button>)}</div>
    <div className="knowledge-panel" role="tabpanel" id={`${id}-mode-panel`} aria-labelledby={`${id}-mode-${active}`} tabIndex={compact ? -1 : 0}>
    <div className="knowledge-composition">
      <div className="example-sources"><span className="knowledge-column-label mono">THE THINGS YOU SAVE</span>
        {memories.map((memory, index) => <button key={memory.title} type="button" tabIndex={compact ? -1 : 0} className={`memory-slip slip-${memory.color}${selected === index ? ' memory-selected' : ''}`} aria-pressed={selected === index} onClick={() => {setSelected(index);setActive(0);setSourceOpen(false);}} data-cursor="READ">
          <div className="memory-slip-meta"><memory.icon size={17} strokeWidth={1.5}/><span className="mono">{memory.type}</span><ArrowUpRight size={14}/></div>
          <strong>{memory.title}</strong><p>{memory.excerpt}</p><span className="memory-tag">{memory.topic}</span>
        </button>)}
      </div>
      <div className="thought-network" aria-hidden="true">
        <svg viewBox="0 0 280 400" fill="none" className="thought-paths">
          <path className="thought-path thought-path-one" d="M0 80C100 80 80 200 140 200"/>
          <path className="thought-path thought-path-two" d="M0 200C60 200 75 200 140 200"/>
          <path className="thought-path thought-path-three" d="M0 320C100 320 80 200 140 200"/>
          <path className="thought-path thought-path-out" d="M140 200C205 200 205 160 280 160"/>
          <path className="thought-signal" d={selected === 0 ? 'M0 80C100 80 80 200 140 200C205 200 205 160 280 160' : selected === 1 ? 'M0 200C60 200 75 200 140 200C205 200 205 160 280 160' : 'M0 320C100 320 80 200 140 200C205 200 205 160 280 160'}/>
          <circle cx="140" cy="200" r="76" className="thought-orbit"/><circle cx="140" cy="200" r="57" className="thought-orbit orbit-inner"/>
          <circle cx="69" cy="172" r="5" className="thought-satellite"/><circle cx="187" cy="258" r="4" className="thought-satellite satellite-two"/>
        </svg>
        <span className="network-topic topic-one">context</span><span className="network-topic topic-two">curiosity</span>
        <div className="thought-core"><Network size={32} strokeWidth={1.1}/><span>YOUR<br/>KNOWLEDGE</span></div>
        <span className="network-footnote mono">A THREAD WORTH FOLLOWING</span>
      </div>
      <div className="example-insight" ref={insight} role="region" aria-label="Example detail" tabIndex={-1} aria-live="polite">
        <div className="insight-kicker mono"><Sparkles size={13}/> {sourceOpen ? 'THE ORIGINAL THOUGHT' : active === 2 ? 'FIND YOUR WAY BACK' : active === 1 ? 'THE CONNECTION' : 'SAVED WITH CONTEXT'}</div>
        {sourceOpen ? <div className="insight-content" key={'source-'+selected}><SourceIcon className="insight-large-icon" size={30} strokeWidth={1.2}/><h3>{source.title}</h3><blockquote>{source.excerpt}</blockquote><p className="example-disclosure">An example source, shown in full.</p><button className="text-button" onClick={() => revealSource(false)} data-cursor="BACK"><ArrowLeft size={14}/> BACK TO THE EXAMPLE</button></div> : active === 0 ? <div className="insight-content" key={'capture-'+selected}><h3>A little less<br/>lost in tabs.</h3><p>Your original thought, its source and the subject it belongs to—kept together.</p><div className="saved-source"><SourceIcon size={17}/><span><strong>{source.title}</strong><small>{source.topic} · example memory</small></span><span className="saved-check">✓</span></div><button className="text-button" onClick={() => revealSource(true)} data-cursor="READ">READ THE THOUGHT <ArrowUpRight size={14}/></button></div> : active === 1 ? <div className="insight-content" key="connect"><h3>Separate notes.<br/>Shared ideas.</h3><div className="connection-example"><span>Learning notes</span><span className="connection-thread"><i/><b>Learning</b><i/></span><span>Research highlights</span></div><p>These two example memories share the tag <strong>Learning</strong>. That gives you a useful thread to follow.</p><button className="text-button" onClick={() => revealSource(true, 2)} data-cursor="FOLLOW">FOLLOW THE CONNECTION <ArrowUpRight size={14}/></button></div> : <div className="insight-content" key="recall"><div className="example-query"><Search size={17}/><span>What helps learning stick?</span></div><Quote size={25} className="recall-quote"/><blockquote>{memories[0].excerpt}</blockquote><button className="source-citation" onClick={() => revealSource(true, 0)} data-cursor="SOURCE"><StickyNote size={15}/><span>Learning notes<small>Example source passage</small></span><ArrowUpRight size={16}/></button></div>}
      </div>
    </div>

    <div className="knowledge-summary"><strong>{modes[active].title}</strong><p>{modes[active].detail}</p></div>
    </div>
  </div>;
}
