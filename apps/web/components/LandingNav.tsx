'use client';

import {useEffect, useRef, useState} from 'react';
import Link from 'next/link';
import {ArrowUpRight, Menu, X} from 'lucide-react';
import Logo from './Logo';

const links = [['PRODUCT', '#features'], ['HOW IT WORKS', '#how'], ['PRIVACY', '#privacy']];
export default function LandingNav() {
  const [open, setOpen] = useState(false);
  const header = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => { if (!header.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', escape); };
  }, [open]);
  return <header className="landing-nav" ref={header}>
    <Logo/>
    <nav aria-label="Main navigation">{links.map(([label, href]) => <a href={href} key={href}>{label}</a>)}<Link href="/login">LOG IN</Link></nav>
    <div className="landing-nav-actions"><Link className="button orange" href="/register" data-cursor="BEGIN">BUILD YOUR VAULT <ArrowUpRight size={17}/></Link><button ref={trigger} className="landing-menu-trigger" onClick={() => setOpen(value => !value)} aria-expanded={open} aria-controls="landing-mobile-navigation" aria-label={open ? 'Close navigation' : 'Open navigation'}>{open ? <X size={20}/> : <Menu size={20}/>}</button></div>
    {open && <div className="landing-mobile-navigation" id="landing-mobile-navigation"><nav aria-label="Mobile navigation">{links.map(([label, href], index) => <a key={href} href={href} onClick={() => setOpen(false)}><span className="mono">0{index + 1}</span>{label}<ArrowUpRight size={18}/></a>)}<Link href="/login" onClick={() => setOpen(false)}><span className="mono">04</span>LOG IN<ArrowUpRight size={18}/></Link></nav></div>}
  </header>;
}
