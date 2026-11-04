'use client';
import { useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, Check, ChevronLeft, GraduationCap, LoaderCircle, RotateCcw } from 'lucide-react';
import { api, post, Doc, Source, date } from '@/lib/api';
type Question = {
    question: string;
    options: string[];
    citation: Source;
};
type Attempt = {
    id: string;
    score: number;
    total: number;
    created: string;
    results?: Array<Question & {
        selected: number;
        correct_answer: number;
        correct: boolean;
        explanation: string;
    }>;
};
type Quiz = {
    id: string;
    document_id: string;
    title: string;
    questions: Question[];
    created: string;
    attempts: Attempt[];
    stale: boolean;
};
export default function QuizRoom({ documents, generation, onSource }: {
    documents: Doc[];
    generation: boolean;
    onSource: (id: string) => void;
}) {
    const [quizzes, setQuizzes] = useState<Quiz[]>([]), [selected, setSelected] = useState<Quiz | null>(null), [answers, setAnswers] = useState<Record<number, number>>({}), [attempt, setAttempt] = useState<Attempt | null>(null), [documentId, setDocumentId] = useState(''), [busy, setBusy] = useState(''), [loading, setLoading] = useState(true), [error, setError] = useState('');
    useEffect(() => { let active = true; api<Quiz[]>('/quizzes').then(r => { if (active)
        setQuizzes(r); }).catch(e => { if (active)
        setError(e.message); }).finally(() => { if (active)
        setLoading(false); }); return () => { active = false; }; }, []);
    async function generate() { setBusy('generate'); setError(''); try {
        const quiz = await post<Quiz>('/quizzes/' + documentId);
        setQuizzes(q => [quiz, ...q]);
        start(quiz);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : 'Quiz generation failed.');
    }
    finally {
        setBusy('');
    } }
    function start(quiz: Quiz) { setSelected(quiz); setAnswers({}); setAttempt(null); setError(''); }
    async function submit(event: React.FormEvent) { event.preventDefault(); if (!selected)
        return; setBusy('submit'); setError(''); try {
        const result = await post<Attempt>('/quizzes/' + selected.id + '/attempts', { answers: selected.questions.map((_, i) => answers[i]) });
        setAttempt(result);
        setQuizzes(await api('/quizzes'));
    }
    catch (e) {
        setError(e instanceof Error ? e.message : 'Your answers could not be saved.');
    }
    finally {
        setBusy('');
    } }
    return <section className="quiz-room"><div className="section-header"><h2><GraduationCap size={20}/> TEST WHAT STUCK</h2><span className="mono">SOURCE-BASED QUIZZES</span></div><p className="muted">Answer first, then check the explanation and the passage behind it. Your attempts stay in your vault.</p><div className="toolbar"><select aria-label="Quiz source document" value={documentId} onChange={e => setDocumentId(e.target.value)}><option value="">Choose a ready document</option>{documents.filter(d => d.status === 'ready').map(d => <option key={d.id} value={d.id}>{d.title}</option>)}</select><button className="button orange" onClick={generate} disabled={!generation || !documentId || !!busy}>{busy === 'generate' ? <><LoaderCircle size={15} className="spin"/> CREATING QUIZ…</> : <>CREATE QUIZ <ArrowRight size={15}/></>}</button></div>{!generation && <p className="fine-print">Quiz generation needs a configured AI provider. Existing quizzes can still be taken.</p>}{error && <p className="error" role="alert">{error}</p>}{selected ? <div className="quiz-active"><div className="section-header"><div><button className="text-button" onClick={() => setSelected(null)}><ChevronLeft size={14}/> ALL QUIZZES</button><h3>{selected.title}</h3></div><span className="mono">{selected.questions.length} QUESTIONS</span></div>{selected.stale && <p className="info">The source changed after this quiz was generated. Past results remain available; generate a fresh quiz to record another attempt.</p>}{attempt ? <><div className="quiz-score" role="status"><span className="mono">ATTEMPT SAVED</span><strong>{attempt.score}<span> / {attempt.total}</span></strong><p>{attempt.score === attempt.total ? 'Every idea connected. Nice work.' : 'A useful place to start. Revisit the passages below.'}</p></div>{attempt.results?.map((result, i) => <article className={'quiz-result ' + (result.correct ? 'correct' : 'review')} key={i}><div className="section-header"><span className="mono">QUESTION {i + 1}</span><span className="status">{result.correct ? 'CORRECT' : 'REVISIT'}</span></div><h4>{result.question}</h4><p>Your answer: <strong>{result.options[result.selected]}</strong></p>{!result.correct && <p>Correct answer: <strong>{result.options[result.correct_answer]}</strong></p>}<p>{result.explanation}</p><button className="text-button" onClick={() => onSource(result.citation.document_id)}>CHECK SOURCE{result.citation.page ? ' · PAGE ' + result.citation.page : ''}<ArrowUpRight size={14}/></button></article>)}<button className="button" onClick={() => start(selected)}><RotateCcw size={15}/> TRY AGAIN</button></> : <form onSubmit={submit}>{selected.questions.map((q, i) => <fieldset className="quiz-question" key={i}><legend><span className="mono">QUESTION {i + 1}</span>{q.question}</legend>{q.options.map((option, j) => <label className={'quiz-option ' + (answers[i] === j ? 'chosen' : '')} key={j}><input type="radio" name={'question-' + i} value={j} required checked={answers[i] === j} onChange={() => setAnswers(a => ({ ...a, [i]: j }))}/><span className="option-letter">{String.fromCharCode(65 + j)}</span><span>{option}</span>{answers[i] === j && <Check size={16}/>}</label>)}</fieldset>)}<div className="quiz-submit"><span className="mono">{Object.keys(answers).length} / {selected.questions.length} ANSWERED</span><button className="button orange" disabled={!!busy || selected.stale || Object.keys(answers).length !== selected.questions.length}>{busy === 'submit' ? 'SAVING ANSWERS…' : 'CHECK MY UNDERSTANDING'}<ArrowRight size={15}/></button></div></form>}</div> : loading ? <p className="muted">Loading your quizzes…</p> : quizzes.length ? <div className="quiz-library">{quizzes.map(quiz => <article className="quiz-card" key={quiz.id}><span className="mono">{quiz.questions.length} QUESTIONS · {date(quiz.created)}</span><h3>{quiz.title}</h3>{quiz.stale && <span className="status pending">SOURCE UPDATED</span>}<p className="muted">{quiz.attempts.length ? `${quiz.attempts.length} attempt${quiz.attempts.length === 1 ? '' : 's'} · Best ${Math.max(...quiz.attempts.map(a => a.score))}/${quiz.questions.length}` : 'Ready for your first attempt.'}</p><div className="button-row"><button className="button compact" onClick={() => start(quiz)}>{quiz.stale ? 'REVIEW QUIZ' : 'TAKE QUIZ'} <ArrowRight size={14}/></button>{quiz.attempts.length > 0 && <button className="text-button" onClick={async () => { setBusy(quiz.id); setError(''); try {
        const results = await api<Attempt[]>('/quizzes/' + quiz.id + '/attempts');
        start(quiz);
        setAttempt(results[0] || null);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : 'Results could not be loaded.');
    }
    finally {
        setBusy('');
    } }} disabled={!!busy}>LAST RESULT</button>}</div></article>)}</div> : <div className="mini-empty"><GraduationCap size={28} strokeWidth={1}/><h3>A LITTLE PRACTICE GOES A LONG WAY.</h3><p>Choose a document to create a quiz grounded in your own material.</p></div>}</section>;
}
