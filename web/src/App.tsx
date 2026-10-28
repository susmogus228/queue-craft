import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import Gantt from './Gantt';
import { HttpError, request } from './api';
import { isRunStale, recordedDecision, resultDescription } from './ui-state';
import { parseImportedJson } from './validation';
import type { Candidate, Evaluation, Instance, Method, Model, Run } from './types';
import { JOB_COLORS, METHODS, methodName, milliseconds, units } from './types';

const terminal = (run: Run | null) => run && !['queued', 'running'].includes(run.status);
const message = (error: unknown) => error instanceof Error ? error.message : 'An unexpected error occurred.';
const fingerprint = (instance: Instance) => JSON.stringify(instance);

function Value({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="value-field"><span>{label}</span><strong>{children}</strong></div>;
}

function ResearchSummary({ model }: { model: Model | null }) {
  const test = model?.evaluation?.test;
  const ood = model?.evaluation?.ood;
  const reference = test?.methods?.cp_sat;
  const learned = test?.methods?.learned;
  const referenceWinsBoth = reference && learned && reference.mean_makespan < learned.mean_makespan && reference.median_wall_ms < learned.median_wall_ms;
  const comparisons = [['spt', 'Shortest processing time'], ['mwkr', 'Most work remaining'], ['fifo', 'FIFO'], ['best_of_rules', 'Best of three rules, per problem'], ['cp_sat', 'CP-SAT reference']] as const;
  function summary(data: Evaluation | undefined, label: string) {
    if (!data) return <p className="muted">No {label.toLowerCase()} evaluation is available.</p>;
    return <section className="research-section"><h3>{label} <span className="muted">· {data.count} problems</span></h3>
      <div className="table-scroll"><table><caption className="sr-only">Learned policy paired comparison on {label}</caption><thead><tr><th>Compared with</th><th>Mean reduction</th><th>95% interval</th><th>Wins / ties / losses</th></tr></thead><tbody>
        {comparisons.map(([id, name]) => { const pair = data.paired?.[id]; const interval = pair?.mean_improvement_ci95_percent; const includesZero = interval && interval[0] <= 0 && interval[1] >= 0; return <tr key={id}><th scope="row">{name}</th><td>{pair ? `${pair.mean_improvement_percent.toFixed(2)}%` : '—'}</td><td>{interval ? `${interval[0].toFixed(2)}% to ${interval[1].toFixed(2)}%` : '—'}{includesZero && <small className="interval-note">Includes zero; no clear mean improvement.</small>}</td><td>{pair ? `${pair.wins} / ${pair.ties} / ${pair.losses}` : '—'}</td></tr>; })}
      </tbody></table></div>
      <p className="caption">Positive reduction means a shorter schedule. Negative means a longer schedule. “Best of three” runs all three rules and selects the shortest result for each problem.</p>
      <div className="table-scroll"><table><caption className="sr-only">Measured schedule quality and construction time on {label}</caption><thead><tr><th>Method</th><th>Mean finish time</th><th>Median construction time</th><th>Valid schedules</th></tr></thead><tbody>{METHODS.map(method => { const record = data.methods?.[method.id]; return <tr key={method.id}><th scope="row">{method.name}</th><td>{units(record?.mean_makespan)}</td><td>{record ? `${record.median_wall_ms.toFixed(2)} ms` : '—'}</td><td>{record ? `${record.valid_count} / ${data.count}` : '—'}</td></tr>; })}</tbody></table></div>
    </section>;
  }
  return <div className="research-view panel"><div className="section-title"><div><span className="eyebrow">Model evidence</span><h2>What the learned policy achieved</h2></div><a className="button secondary" href="/research" target="_blank" rel="noreferrer">Full research report ↗</a></div>
    <p>This is a supervised operation-ranking experiment on generated, static job-shop problems. It does not establish industrial performance or general superiority over mathematical optimization.</p>
    {model?.ready && <p className="model-line"><span className="status-dot ready" />Artifact {model.version ?? 'available'} · {model.training_summary?.instances ?? '—'} training problems · {model.training_summary?.fits ?? '—'} fitted configurations</p>}
    {!model?.ready && <p className="notice">The trained artifact is not available. Baseline comparisons remain usable; there are no ML results to infer from them.</p>}
    {summary(test, 'Frozen test')}{summary(ood, 'Different problem sizes')}
    <section className="research-section"><h3>Read the limitations</h3><p>Compare measured runtime as well as makespan. {referenceWinsBoth ? 'In the frozen test, CP-SAT achieved a lower mean finish time and a lower median runtime than the learned policy. This experiment does not demonstrate solver acceleration.' : 'The learned model may be slower or produce a longer schedule than the mathematical reference.'} Scores in the inspector are ranking values, not probabilities or guarantees of optimality.</p>
    <p>Known durations, fixed machines, non-preemptive operations and a makespan objective. Changing a duration creates a new plan before work starts; it does not model a surprise breakdown during production.</p>
    {model?.limitations?.length ? <ul>{model.limitations.map((limitation, i) => <li key={i}>{limitation}</li>)}</ul> : null}
    <a href="/docs" target="_blank" rel="noreferrer">Explore the documented API ↗</a></section>
  </div>;
}

export default function App() {
  const [examples, setExamples] = useState<Instance[]>([]);
  const [instance, setInstance] = useState<Instance | null>(null);
  const [model, setModel] = useState<Model | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState('');
  const [modelError, setModelError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [bootKey, setBootKey] = useState(0);
  const [tab, setTab] = useState<'plan' | 'research'>('plan');
  const [run, setRun] = useState<Run | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [pollKey, setPollKey] = useState(0);
  const [pollError, setPollError] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [method, setMethod] = useState<Method>('learned');
  const [selected, setSelected] = useState('');
  const [duration, setDuration] = useState('');
  const [solverSeconds, setSolverSeconds] = useState('2');
  const [replayStep, setReplayStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [exporting, setExporting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const comparisonRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => { setReducedMotion(media.matches); if (media.matches) setPlaying(false); };
    update(); media.addEventListener('change', update); return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    let ignore = false;
    const controller = new AbortController(); setLoading(true); setBootError(''); setModelError('');
    Promise.allSettled([request<{ examples: Instance[] }>('/api/examples', { signal: controller.signal }), request<Model>('/api/model', { signal: controller.signal })]).then(([problems, info]) => {
      if (ignore) return;
      if (problems.status === 'fulfilled' && Array.isArray(problems.value.examples)) {
        setExamples(problems.value.examples);
        setInstance(current => current ?? problems.value.examples[0] ?? null);
        if (!problems.value.examples.length) setBootError('The server has no example problems. Import a JSON instance to begin.');
      } else setBootError(problems.status === 'rejected' ? message(problems.reason) : 'The server returned an invalid example list.');
      if (info.status === 'fulfilled') setModel(info.value); else { setModel(null); setModelError(message(info.reason)); }
      setLoading(false);
    });
    return () => { ignore = true; controller.abort(); };
  }, [bootKey]);

  const busy = submitting || !!run && !terminal(run);
  const stale = isRunStale(run, instance, Number(solverSeconds));
  const result = run?.results.find(record => record.method === method) ?? null;
  const allOperations = useMemo(() => instance?.jobs.flatMap(job => job.operations.map((operation, index) => ({ ...operation, id: `${job.id}.${index + 1}`, job_id: job.id, index }))) ?? [], [instance]);
  const selectedInput = allOperations.find(operation => operation.id === selected) ?? allOperations[0];
  const selectedScheduled = result?.operations.find(operation => operation.id === selected);
  const trace = result?.trace.find(item => item.step === replayStep);
  const inputTrace = recordedDecision(result?.trace ?? [], replayStep, selected);
  const candidate: Candidate | undefined = inputTrace?.candidates.find(item => item.id === selected);

  useEffect(() => { if (selectedInput) setDuration(String(selectedInput.duration)); }, [selectedInput?.id, selectedInput?.duration]);

  useEffect(() => {
    if (!run || terminal(run)) return;
    let ignore = false; let timeout: number; const controller = new AbortController(); setPollError('');
    const poll = async () => {
      try {
        const updated = await request<Run>(`/api/runs/${encodeURIComponent(run.id)}`, { signal: controller.signal });
        if (ignore) return;
        setRun(updated);
        if (!terminal(updated)) timeout = window.setTimeout(poll, 400);
        else setCancelling(false);
      } catch (failure) {
        if (!ignore && failure instanceof HttpError && failure.status === 404) {
          setRun(null); setPlaying(false); setCancelling(false);
          setNotice('This run expired or the server restarted. Your problem is kept; compare again.');
        } else if (!ignore) setPollError(message(failure));
      }
    };
    timeout = window.setTimeout(poll, 150);
    return () => { ignore = true; window.clearTimeout(timeout); controller.abort(); };
  }, [run?.id, pollKey]);

  useEffect(() => {
    if (!run || !terminal(run)) return;
    const preferred = run.results.find(item => item.method === 'learned' && item.operations.length) ?? run.results.find(item => item.operations.length);
    if (preferred) { setMethod(preferred.method); setReplayStep(preferred.trace.length); setSelected(preferred.trace.at(-1)?.chosen_id ?? preferred.operations[0].id); }
    setPlaying(false);
  }, [run?.id, run?.status]);

  useEffect(() => {
    if (!playing || !result?.trace.length || reducedMotion || stale) return;
    const timeout = window.setInterval(() => {
      const next = Math.min(replayStep + 1, result.trace.length);
      setReplayStep(next);
      const chosen = result.trace.find(item => item.step === next)?.chosen_id;
      if (chosen) setSelected(chosen);
      if (next >= result.trace.length) setPlaying(false);
    }, 700);
    return () => window.clearInterval(timeout);
  }, [playing, replayStep, result?.method, result?.trace.length, reducedMotion, stale]);

  function chooseProblem(problem: Instance) {
    setInstance(structuredClone(problem)); setSelected(`${problem.jobs[0].id}.1`); setRun(null); setError(''); setNotice(''); setPollError(''); setPlaying(false); setReplayStep(0);
  }

  async function startComparison() {
    if (!instance || busy) return;
    const budget = Number(solverSeconds);
    if (!Number.isFinite(budget) || budget < 0.1 || budget > 5) { setError('Solver budget must be between 0.1 and 5 seconds.'); return; }
    setSubmitting(true); setError(''); setNotice(''); setPollError(''); setPlaying(false); setCancelling(false);
    try {
      const created = await request<Run>('/api/runs', { method: 'POST', body: JSON.stringify({ instance, strategies: METHODS.map(item => item.id), solver_seconds: budget }) });
      setRun(created); setReplayStep(0);
    } catch (failure) { setError(message(failure)); } finally { setSubmitting(false); }
  }

  async function cancelRun() {
    if (!run || !busy || cancelling) return;
    setCancelling(true); setError('');
    try {
      const updated = await request<Run | {id: string; status: 'removed'}>(`/api/runs/${encodeURIComponent(run.id)}`, { method: 'DELETE' });
      if (updated.status === 'removed') {
        setRun(null); setPlaying(false); setNotice('The run had already finished and has been removed. You can compare again.');
      } else { setRun(updated); setPollKey(key => key + 1); }
      setCancelling(false);
    } catch (failure) {
      if (failure instanceof HttpError && failure.status === 404) {
        setRun(null); setPlaying(false); setNotice('This run is no longer available. Your problem is kept.');
      } else setError(message(failure));
      setCancelling(false);
    }
  }

  function resetUnavailableRun() {
    const previous = run;
    setRun(null); setPollError(''); setPlaying(false); setCancelling(false);
    setNotice('The unavailable run is no longer tracked. Your problem is kept; compare again.');
    if (previous) void request(`/api/runs/${encodeURIComponent(previous.id)}`, {method:'DELETE'}).catch(() => undefined);
  }

  function saveProblem() {
    if (!instance) return;
    const url = URL.createObjectURL(new Blob([`${JSON.stringify(instance, null, 2)}\n`], {type:'application/json'}));
    const anchor = document.createElement('a'); anchor.href=url; anchor.download='queuecraft-problem.json'; anchor.click();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function applyChange(event: FormEvent) {
    event.preventDefault(); if (!instance || !selectedInput || busy) return;
    const value = Number(duration);
    if (!Number.isInteger(value) || value < 1 || value > 1000) { setError('Duration must be a whole number from 1 to 1000 time units.'); return; }
    setInstance({ ...instance, jobs: instance.jobs.map(job => job.id === selectedInput.job_id ? { ...job, operations: job.operations.map((operation, index) => index === selectedInput.index ? { ...operation, duration: value } : operation) } : job) });
    setPlaying(false); setError(''); setNotice('Duration updated. Run the comparison to calculate a new plan.');
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = ''; if (!file || busy) return;
    setError('');
    try {
      if (file.size > 128 * 1024) throw new Error('The JSON file is too large. Maximum size: 128 KiB.');
      const problem = parseImportedJson(await file.text()); chooseProblem(problem); setNotice(`Imported “${problem.name}”. Ready to compare.`);
    } catch (failure) { setError(message(failure)); }
  }

  async function exportReport() {
    if (!run || !terminal(run) || !run.results.length) return;
    setExporting(true); setError('');
    try {
      const report = await request<unknown>(`/api/runs/${encodeURIComponent(run.id)}/export`);
      const blob = new Blob([`${JSON.stringify(report, null, 2)}\n`], { type: 'application/json' }); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `queuecraft-${run.id}.json`; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setError(message(failure)); } finally { setExporting(false); }
  }

  function selectMethod(id: Method) {
    setMethod(id); setPlaying(false);
    const next = run?.results.find(item => item.method === id); setReplayStep(next?.trace.length ?? 0);
  }
  function moveReplay(next: number) {
    setPlaying(false); setReplayStep(next);
    const chosen = result?.trace.find(item => item.step === next)?.chosen_id; if (chosen) setSelected(chosen);
  }
  function togglePlay() {
    if (!result?.trace.length) return;
    if (replayStep >= result.trace.length) { setReplayStep(0); setSelected(result.trace[0]?.chosen_id ?? selected); }
    setPlaying(current => !current);
  }

  const summary = instance ? `${instance.jobs.length} jobs · ${instance.machines} machines · ${allOperations.length} operations` : 'No problem loaded';
  const exampleIndex = instance ? examples.findIndex(item => fingerprint(item) === fingerprint(instance)) : -1;
  return <>
    <a href="#workspace" className="skip-link">Skip to workspace</a>
    <header className="app-header"><a className="wordmark" href="#" onClick={() => setTab('plan')}>Queue<span>Craft</span><i /></a>
      <nav aria-label="Main navigation"><button className={tab === 'plan' ? 'nav-active' : ''} onClick={() => setTab('plan')}>Plan</button><button onClick={() => { setTab('plan'); window.setTimeout(() => comparisonRef.current?.scrollIntoView({ behavior: reducedMotion ? 'instant' : 'smooth', block: 'start' }), 0); }}>Compare</button><button className={tab === 'research' ? 'nav-active' : ''} onClick={() => setTab('research')}>Research</button><a href="/docs" target="_blank" rel="noreferrer">API ↗</a></nav>
      <span className="workspace-badge"><i className="status-dot ready" />Local workspace<span className="control-room">Control Room</span></span>
    </header>
    <main id="workspace" tabIndex={-1}>
      <div className="workspace-title"><div><span className="eyebrow">Learned dispatching / scheduling research</span><h1>{tab === 'research' ? 'Evidence and limitations' : 'Production planner'}</h1></div><p>One problem. Five scheduling strategies.</p></div>
      {error && <div className="alert error" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
      {notice && <div className="alert notice" role="status"><span>{notice}</span><button aria-label="Dismiss notice" onClick={() => setNotice('')}>×</button></div>}
      {bootError && <div className="alert error" role="alert"><span>{bootError}</span><button onClick={() => setBootKey(key => key + 1)}>Retry connection</button></div>}
      {modelError && <div className="alert warning" role="status"><span>Model metadata unavailable. {modelError} Baselines can still run.</span><button onClick={() => setBootKey(key => key + 1)}>Retry</button></div>}
      {tab === 'research' ? <ResearchSummary model={model} /> : <div className="workspace-grid">
        <aside className="panel scenario-panel" aria-label="Scenario setup"><h2>Scenario setup</h2>
          <div className="panel-section"><label htmlFor="example-select">Problem</label><select id="example-select" value={exampleIndex} disabled={busy || loading || !examples.length} onChange={event => { const example = examples[Number(event.target.value)]; if (example) chooseProblem(example); }}>{exampleIndex < 0 && <option value={-1}>{instance ? `${instance.name} (modified / imported)` : loading ? 'Loading examples…' : 'Choose a problem'}</option>}{examples.map((example, index) => <option value={index} key={index}>{example.name}</option>)}</select><p className="problem-count">{summary}</p>
          <div className="route-list">{instance?.jobs.map((job, index) => <div className="job-route" key={job.id}><div className="route-label"><i className="job-swatch" style={{ background: JOB_COLORS[index % JOB_COLORS.length] }} /><strong>{job.id}</strong><span>{job.operations.length} operations</span></div><p>{job.operations.map(op => `M${op.machine + 1} (${op.duration})`).join(' → ')}</p></div>) ?? <p className="caption">{loading ? 'Getting example problems from the local server…' : 'Load a problem to see its operation routes.'}</p>}</div>
          <input className="sr-only" ref={fileInput} type="file" accept=".json,application/json" aria-label="Import a JSON problem" onChange={importFile} disabled={busy} />
          <button className="button full secondary" disabled={busy} onClick={() => fileInput.current?.click()}><span aria-hidden="true">↥</span> Import JSON<span className="button-end" aria-hidden="true">›</span></button><p className="caption">Instance or exported report · up to 128 KiB. Files stay on this local server.</p>
          <button className="button full subtle" disabled={busy || !examples.length} onClick={() => chooseProblem(examples[0])}>Reset to example</button></div>
          <form className="panel-section operation-editor" onSubmit={applyChange}><h3>Edit operation</h3><label htmlFor="operation-select">Selected operation</label><select id="operation-select" value={selectedInput?.id ?? ''} disabled={busy || !allOperations.length} onChange={event => { setSelected(event.target.value); setPlaying(false); }}>{allOperations.map(op => <option key={op.id} value={op.id}>{op.id}</option>)}</select>
          <div className="inline-facts"><span>Job <strong>{selectedInput?.job_id ?? '—'}</strong></span><span>Machine <strong>{selectedInput ? `M${selectedInput.machine + 1}` : '—'}</strong></span></div>
          <label htmlFor="duration">Duration <span className="muted">(time units)</span></label><input id="duration" type="number" min={1} max={1000} step={1} value={duration} disabled={busy || !selectedInput} onChange={event => setDuration(event.target.value)} />
          <button type="submit" className="button full primary" disabled={busy || !selectedInput || Number(duration) === selectedInput.duration}>Apply change</button><p className="caption">Recompute before execution. Editing does not update an existing schedule.</p></form>
          <div className="panel-section solver-settings"><h3>Reference budget</h3><label htmlFor="solver-budget">CP-SAT time limit <span className="muted">(seconds)</span></label><input id="solver-budget" type="number" min="0.1" max="5" step="0.1" value={solverSeconds} disabled={busy} onChange={event => setSolverSeconds(event.target.value)} /><p className="caption">0.1–5 seconds. A time-limited solution may not be proven optimal.</p></div>
        </aside>
        <div className="center-column">
          <section className={`panel schedule-panel ${stale ? 'stale-panel' : ''}`} aria-label="Schedule"><div className="section-title"><div><h2>{result?.operations.length ? `${methodName(method)} schedule` : 'Schedule'}</h2><p className="caption">{result?.operations.length ? `${stale ? 'Previous input · ' : ''}Select an operation for its details.` : 'Schedules are calculated by the local API.'}</p></div><span className="mono muted">Time units</span></div>
            {stale && <div className="inline-notice" role="status">Problem or solver budget changed. This is the previous plan; run the comparison again.</div>}
            {instance && result?.operations.length ? <><div className="schedule-stats"><span><small>Finish time</small><strong>{units(result.makespan)}<em> units</em></strong></span><span><small>Construction</small><strong>{milliseconds(result.wall_seconds)}</strong></span><span><small>Constraints</small><strong className={result.validation.valid ? 'good-text' : 'bad-text'}>{result.validation.valid ? 'Valid' : 'Failed'}</strong></span></div><Gantt instance={run?.instance ?? instance} result={result} selected={selected} replayStep={replayStep} onSelect={id => { setSelected(id); setPlaying(false); }} /></> : <div className="empty-schedule" aria-live="polite"><div className="empty-lanes" aria-hidden="true"><span /><span /><span /></div><h3>{loading ? 'Connecting to the workspace' : busy ? 'Building the schedules' : result ? 'No schedule for this method' : 'Start with a comparison'}</h3><p>{result?.error ?? (busy ? 'Each strategy uses the same jobs and constraints. Elapsed time is shown below.' : 'Choose an example or import your jobs, then compare all five strategies.')}</p>{!busy && !loading && !result && <button className="button primary" onClick={startComparison} disabled={!instance}>Compare strategies</button>}</div>}
            {result?.operations.length ? <details className="schedule-table"><summary>Schedule as a table</summary><div className="table-scroll"><table><thead><tr><th>Operation</th><th>Machine</th><th>Start</th><th>End</th><th>Duration</th></tr></thead><tbody>{result.operations.map(op => <tr key={op.id}><th scope="row"><button className="text-button" onClick={() => { setSelected(op.id); setPlaying(false); }}>{op.id}</button></th><td>M{op.machine + 1}</td><td>{op.start}</td><td>{op.end}</td><td>{op.duration}</td></tr>)}</tbody></table></div></details> : null}
            {result?.validation.errors.length ? <p className="bad-text" role="alert">{result.validation.errors.join(' ')}</p> : null}
          </section>
          <section className="panel comparison-panel" ref={comparisonRef} aria-label="Compare scheduling strategies"><div className="section-title compare-title"><div><h2>Compare scheduling strategies</h2><p className="caption">Shorter finish time is better. Runtime is measured separately.</p></div><button className="button primary" onClick={startComparison} disabled={busy || !instance}>{busy ? 'Calculating…' : 'Compare strategies'}</button></div>
            <div className="comparison-status"><span><i className={`status-dot ${model?.ready ? 'ready' : ''}`} />Model: {model?.ready ? `ready · v${model.version ?? '—'}` : loading ? 'checking…' : 'not available'}</span>{run && <span className="mono">{run.status} · {run.elapsed_seconds.toFixed(2)} s</span>}{busy && <button className="text-button" disabled={cancelling || submitting} onClick={cancelRun}>{cancelling ? 'Cancelling…' : 'Cancel run'}</button>}</div>
            {pollError && <div className="inline-notice error" role="alert">{pollError} <button className="text-button" onClick={() => setPollKey(key => key + 1)}>Retry status</button> <button className="text-button" onClick={resetUnavailableRun}>Reset unavailable run</button></div>}
            {run?.error && <div className="inline-notice error" role="alert">{run.error}</div>}
            {run?.status === 'cancelled' && <div className="inline-notice" role="status">Run cancelled. Any completed strategy results remain available.</div>}
            <div className="table-scroll"><table className="comparison-table"><caption className="sr-only">Strategy results. Select a method to inspect its schedule.</caption><thead><tr><th>Method</th><th>Finish time</th><th>Runtime</th><th>Status</th></tr></thead><tbody>{METHODS.map(item => {
              const record = run?.results.find(row => row.method === item.id); const hasSchedule = !!record?.operations.length;
              return <tr key={item.id} className={method === item.id && record ? 'selected-method' : ''}><th scope="row"><button className="method-button" aria-pressed={method === item.id && !!record} disabled={!record} onClick={() => selectMethod(item.id)}><span>{item.name}</span><small>{item.description}</small></button></th><td className="mono finish-time">{units(record?.makespan)}</td><td className="mono">{record ? milliseconds(record.wall_seconds) : '—'}</td><td><span className={`result-status ${hasSchedule ? 'has-schedule' : record?.status === 'ERROR' ? 'bad-text' : ''}`}>{record?.status ?? (busy ? 'Pending' : 'Not run')}</span></td></tr>;
            })}</tbody></table></div>
            {result && <div className="result-note"><span>{resultDescription(result)}</span>{result.best_bound != null && <span className="mono">Lower bound: {units(result.best_bound)}</span>}{result.error && <span className="bad-text">{result.error}</span>}</div>}
            {run && <p className="caption">CP-SAT budget for this run: {run.solver_seconds} seconds.</p>}
            <div className="comparison-footer"><span className="caption">{stale ? 'Report contains the original input and budget for this run.' : 'Save a compact problem for import; reports include full traces.'}</span><div className="export-actions"><button className="button secondary" onClick={saveProblem} disabled={!instance || busy}>Save problem</button><button className="button secondary" onClick={exportReport} disabled={exporting || !run || !terminal(run) || !run.results.length}>{exporting ? 'Preparing…' : 'Export report'}</button></div></div>
          </section>
        </div>
        <aside className="panel inspector-panel" aria-label="Decision inspector"><h2>Decision replay</h2><p className="inspector-description">{result?.trace.length ? `Dispatch trace · step ${replayStep} of ${result.trace.length}` : result?.method === 'cp_sat' && result.operations.length ? 'Reference schedule · no dispatch trace' : 'Run a strategy to inspect its decisions.'}</p>
          <div className="replay-controls"><button aria-label="Previous decision" disabled={!result?.trace.length || replayStep <= 0 || stale} onClick={() => moveReplay(Math.max(0, replayStep - 1))}>‹</button><button aria-label={playing ? 'Pause replay' : 'Play replay'} disabled={!result?.trace.length || reducedMotion || stale} onClick={togglePlay}>{playing ? 'Ⅱ' : '▶'}</button><button aria-label="Next decision" disabled={!result?.trace.length || replayStep >= result.trace.length || stale} onClick={() => moveReplay(Math.min(result?.trace.length ?? 0, replayStep + 1))}>›</button></div>
          {reducedMotion && <p className="caption">Reduced motion is enabled. Use the previous and next controls to step through decisions.</p>}
          {result?.trace.length ? <div className="step-control"><label htmlFor="replay-step">Construction step <span>{replayStep} / {result.trace.length}</span></label><input id="replay-step" type="range" min={0} max={result.trace.length} value={replayStep} disabled={stale} onChange={event => moveReplay(Number(event.target.value))} /></div> : <div className="replay-track" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /><i /></div>}
          <div className="panel-section decision-inputs"><h3>{result?.method === 'cp_sat' ? 'Operation details' : 'Decision inputs'}</h3><Value label="Selected operation">{selectedInput?.id ?? '—'}</Value><div className="two-values"><Value label="Machine">{selectedInput ? `M${selectedInput.machine + 1}` : '—'}</Value><Value label="Duration">{selectedInput?.duration ?? '—'}</Value></div><Value label="Earliest start (time units)">{stale ? 'Recompute required' : candidate?.earliest_start ?? '—'}</Value><Value label="Remaining job work">{stale ? '—' : candidate?.remaining_work ?? '—'}</Value><Value label="Model rank score">{!stale && candidate?.score != null ? candidate.score.toFixed(4) : '—'}</Value>
          {selectedScheduled && <p className="caption">{stale ? 'Previous plan: ' : 'Scheduled: '}{selectedScheduled.start}–{selectedScheduled.end} time units.</p>}
          <p className="inspector-note">Inputs and rank scores are not a proof of optimality.</p>
          {inputTrace && !stale && <p className="caption">Selected inputs recorded at construction step {inputTrace.step}.</p>}
          {candidate?.features && !stale && <details className="feature-details"><summary>All recorded features</summary><dl>{Object.entries(candidate.features).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{Number.isFinite(value) ? value.toFixed(4) : String(value)}</dd></div>)}</dl></details>}</div>
          {trace && !stale && <div className="panel-section candidates"><h3>Candidates at step {trace.step}</h3><p className="caption">Chosen: {trace.chosen_id}. These were the eligible next operations.</p><div className="candidate-list">{trace.candidates.map(item => <button key={item.id} className={item.id === selected ? 'active-candidate' : ''} onClick={() => { setSelected(item.id); setPlaying(false); }}><span>{item.id}{item.id === trace.chosen_id ? ' · chosen' : ''}</span><small>{item.score == null ? `duration ${item.duration}` : `score ${item.score.toFixed(3)}`}</small></button>)}</div></div>}
          <div className="panel-section next-step"><h3>What to try</h3><p>Change an operation’s duration, then compare again. The best strategy can depend on the problem.</p><button className="text-button" onClick={() => setTab('research')}>View model evidence →</button></div>
        </aside>
      </div>}
    </main>
    <footer className="app-footer"><span>QueueCraft <span className="muted">/</span> Local CPU scheduling workbench</span><span>Static planning · known durations · no live factory connection</span><a href="/docs" target="_blank" rel="noreferrer">OpenAPI ↗</a></footer>
  </>;
}
