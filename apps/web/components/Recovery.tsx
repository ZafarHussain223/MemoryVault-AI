'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import Logo from './Logo';
import {post} from '@/lib/api';
export default function Recovery({mode}:{mode:'forgot-password'|'reset-password'|'verify'}){
 const [token,setToken]=useState(''),[message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[ready,setReady]=useState(false);
 useEffect(()=>{setToken(new URLSearchParams(window.location.search).get('token')||'');setReady(true)},[]);
 async function submit(e:React.FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError('');try{const data=Object.fromEntries(new FormData(e.currentTarget));const result=await post<{message:string}>('/auth/'+mode,{...data,token});setMessage(result.message)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <main className="recovery-page"><Logo/><section className="panel"><span className="mono label">[ YOUR ACCOUNT ]</span><h1>{mode==='verify'?'VERIFY YOUR EMAIL.':mode==='reset-password'?'A FRESH START.':'RECOVER YOUR VAULT.'}</h1>{message?<><p role="status">{message}</p><Link className="button orange" href="/login">RETURN TO SIGN IN ↗</Link></>:<form method="post" onSubmit={submit}>{mode==='forgot-password'?<label>Email address<input disabled={!ready||busy} type="email" name="email" autoComplete="email" required/></label>:mode==='reset-password'?<label>New password<input disabled={!ready||busy} type="password" name="password" minLength={10} maxLength={128} autoComplete="new-password" required/></label>:<p>Confirm your email using the link sent to your inbox.</p>}{error&&<p role="alert" className="error">{error}</p>}<button className="button orange" disabled={!ready||busy||(mode!=='forgot-password'&&!token)}>{busy?'PLEASE WAIT…':mode==='verify'?'VERIFY EMAIL':mode==='reset-password'?'SET NEW PASSWORD':'SEND RESET INSTRUCTIONS'}</button></form>}<p><Link className="small-link" href="/login">← BACK TO SIGN IN</Link></p></section></main>
}
