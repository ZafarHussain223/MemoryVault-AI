'use client';
import {useEffect, useRef} from 'react';
import {ArrowDownRight, FileText, Link2, StickyNote} from 'lucide-react';

const words = ['You', 'don’t', 'need', 'to', 'remember', 'everything.', 'Just', 'how', 'it', 'connects.'];
export default function KnowledgeStory() {
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = section.current;
    if (!element) return;
    const text = [...element.querySelectorAll<HTMLElement>('.ink-word')];
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let visible = true;
    function paint() {
      frame = 0;
      if (!element) return;
      const staticMode = reduced.matches || document.documentElement.dataset.motion === 'off';
      const rect = element.getBoundingClientRect();
      const value = staticMode ? 1 : Math.max(0, Math.min(1, (innerHeight * .78 - rect.top) / Math.max(440, rect.height * .74)));
      element.style.setProperty('--story-progress', String(value));
      element.style.setProperty('--story-fill', `${value * 100}%`);
      text.forEach((word, index) => word.style.setProperty('--word-fill', `${Math.max(0, Math.min(1, value * text.length - index)) * 100}%`));
    }
    function queue() { if (visible && !document.hidden && !frame) frame = requestAnimationFrame(paint); }
    const observer = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; if (visible) queue(); }, {rootMargin:'120px'});
    observer.observe(element);
    const preference = new MutationObserver(() => { paint(); });
    preference.observe(document.documentElement, {attributes:true, attributeFilter:['data-motion']});
    addEventListener('scroll', queue, {passive:true}); addEventListener('resize', queue);
    reduced.addEventListener('change', paint); document.addEventListener('visibilitychange', queue);
    paint();
    return () => {cancelAnimationFrame(frame);observer.disconnect();preference.disconnect();removeEventListener('scroll',queue);removeEventListener('resize',queue);reduced.removeEventListener('change',paint);document.removeEventListener('visibilitychange',queue);};
  }, []);
  return <section ref={section} className="knowledge-story" id="features" aria-labelledby="story-title" data-motion-scene>
    <div className="story-color-wash" aria-hidden="true"/>
    <div className="story-overline mono"><span>[ 01 / THE WAY IDEAS WORK ]</span><ArrowDownRight size={23} strokeWidth={1}/></div>
    <h2 id="story-title">{words.map((word,index) => <span className={'ink-word' + (index === words.length-1 ? ' ink-emphasis' : '')} key={index}>{word}{' '}</span>)}</h2>
    <div className="story-understanding"><p>That paragraph you saved. The question in your notes. An idea you haven’t quite finished.<br/><strong>Bring them together. See what comes next.</strong></p><div className="story-thoughts" aria-hidden="true"><span className="thought-token token-note"><StickyNote size={18}/> a thought</span><span className="thought-token token-source"><FileText size={18}/> a source</span><span className="thought-token token-link"><Link2 size={18}/> a connection</span></div></div>
    <div className="story-thread" aria-hidden="true"><svg viewBox="0 0 1000 55" preserveAspectRatio="none" fill="none"><path className="story-thread-base" d="M8 26H992"/><path className="story-thread-fill" pathLength="1" d="M8 26H992"/>{[8,500,992].map(x => <circle key={x} cx={x} cy="26" r="5"/>)}</svg></div>
    <div className="story-thread-labels mono"><span>CAPTURE THE SPARK</span><span>KEEP THE CONTEXT</span><span>RETURN WITH AN IDEA</span></div>
  </section>;
}
