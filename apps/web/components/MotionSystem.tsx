'use client';

import {useEffect, useRef, useState} from 'react';
import {usePathname} from 'next/navigation';
import KnowledgeCursor from './KnowledgeCursor';

/** Progressive enhancement: content remains visible without animation or JavaScript. */
export default function MotionSystem() {
  const pathname = usePathname();
  const progress = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(true);
  const [systemReduced, setSystemReduced] = useState(false);

  useEffect(() => {
    const query = matchMedia('(prefers-reduced-motion: reduce)');
    const sync = () => setSystemReduced(query.matches);
    sync();
    query.addEventListener('change', sync);
    try { setEnabled(localStorage.getItem('memoryvault-motion') !== 'off'); } catch { /* Storage is optional. */ }
    return () => query.removeEventListener('change', sync);
  }, []);

  useEffect(() => {
    const active = enabled && !systemReduced;
    document.documentElement.dataset.motion = active ? 'on' : 'off';
    const targets = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'));
    if (!active) {
      targets.forEach(el => el.classList.remove('reveal-waiting'));
      return;
    }
    // Only hide offscreen sections after observation is available. The hero never waits.
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.remove('reveal-waiting');
        entry.target.classList.add('reveal-arrived');
        observer.unobserve(entry.target);
      }
    }, {threshold: 0.08, rootMargin: '0px 0px -24px 0px'});
    targets.forEach(el => {
      if (el.getBoundingClientRect().top > innerHeight - 24) el.classList.add('reveal-waiting');
      observer.observe(el);
    });
    return () => {
      observer.disconnect();
      targets.forEach(el => el.classList.remove('reveal-waiting', 'reveal-arrived'));
    };
  }, [pathname, enabled, systemReduced]);

  useEffect(() => {
    let frame = 0;
    const paint = () => {
      frame = 0;
      const height = document.documentElement.scrollHeight - innerHeight;
      progress.current?.style.setProperty('transform', `scaleX(${height > 0 ? scrollY / height : 0})`);
    };
    const queue = () => { if (!frame) frame = requestAnimationFrame(paint); };
    queue();
    addEventListener('scroll', queue, {passive: true});
    addEventListener('resize', queue);
    const resize = new ResizeObserver(queue);
    resize.observe(document.body);
    return () => {
      cancelAnimationFrame(frame);
      removeEventListener('scroll', queue);
      removeEventListener('resize', queue);
      resize.disconnect();
    };
  }, [pathname]);

  useEffect(() => {
    const scenes = Array.from(document.querySelectorAll<HTMLElement>('[data-motion-scene]'));
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) entry.target.classList.toggle('is-motion-outside', !entry.isIntersecting);
    }, {rootMargin: '100px'});
    scenes.forEach(scene => observer.observe(scene));
    const visibility = () => { document.documentElement.dataset.pageVisible = String(!document.hidden); };
    visibility();
    document.addEventListener('visibilitychange', visibility);
    return () => {
      observer.disconnect();
      scenes.forEach(scene => scene.classList.remove('is-motion-outside'));
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [pathname]);
  function toggleMotion() {
    setEnabled(value => {
      try { localStorage.setItem('memoryvault-motion', value ? 'off' : 'on'); } catch { /* Optional preference storage. */ }
      return !value;
    });
  }

  return <>
    <div className="reading-progress" ref={progress} aria-hidden="true"/>
    <KnowledgeCursor enabled={enabled && !systemReduced && pathname === "/"}/>
    {pathname === '/' && <button className="motion-control mono" onClick={toggleMotion} aria-pressed={enabled && !systemReduced} disabled={systemReduced} aria-label={systemReduced ? 'Reduced motion follows your device settings' : `Turn animations ${enabled ? 'off' : 'on'}`}><span className="motion-bars" aria-hidden="true"><b/><b/><b/></span>{systemReduced ? 'REDUCED MOTION' : `MOTION ${enabled ? 'ON' : 'OFF'}`}</button>}
  </>;
}
