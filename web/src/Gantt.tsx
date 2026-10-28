import type { Instance, Result, ScheduledOperation } from './types';
import { JOB_COLORS, units } from './types';

interface Props { instance: Instance; result: Result; selected: string; replayStep: number; onSelect: (id: string) => void }
export default function Gantt({ instance, result, selected, replayStep, onSelect }: Props) {
  const maximum = Math.max(result.makespan ?? 1, 1);
  const rough = maximum / 6;
  const power = 10 ** Math.floor(Math.log10(rough));
  const interval = [1, 2, 5, 10].map(value => value * power).find(value => value >= rough) ?? power * 10;
  const horizon = Math.ceil(maximum / interval) * interval;
  const ticks = Array.from({ length: Math.round(horizon / interval) + 1 }, (_, i) => i * interval);
  const width = Math.max(660, Math.min(1200, result.operations.length * 25));
  const left = 48, top = 38, lane = 74, right = 20, plot = width - left - right;
  const height = top + instance.machines * lane + 16;
  const x = (time: number) => left + (time / horizon) * plot;
  const current = result.trace?.find(trace => trace.step === replayStep);
  const chosen = result.operations.find(op => op.id === current?.chosen_id);
  const label = (op: ScheduledOperation) => `${op.id}: machine ${op.machine + 1}, starts ${op.start}, ends ${op.end}, duration ${op.duration} time units`;
  return <>
    <div className="timeline-scroll" tabIndex={0} role="region" aria-label="Schedule timeline, horizontally scrollable">
      <svg className="gantt" viewBox={`0 0 ${width} ${height}`} style={{ minWidth: width }} role="group" aria-label={`${result.label} schedule. Select an operation for details.`}>
        <defs><pattern id="bar-stripe" patternUnits="userSpaceOnUse" width="7" height="7"><path d="M0 7 7 0" stroke="#111" strokeOpacity=".12" /></pattern>{result.operations.map(op => <clipPath id={`clip-${op.id}`} key={op.id}><rect x={x(op.start)} y={top + op.machine * lane} width={Math.max((op.duration / horizon) * plot - 3, 1)} height={53} /></clipPath>)}</defs>
        {ticks.map(tick => <g key={tick}><line x1={x(tick)} x2={x(tick)} y1={top - 9} y2={height - 8} className="chart-grid" /><text x={x(tick)} y={18} className="chart-tick" textAnchor="middle">{units(tick)}</text></g>)}
        {Array.from({ length: instance.machines }, (_, machine) => <g key={machine}><text x={0} y={top + machine * lane + 30} className="machine-label">M{machine + 1}</text><line x1={left} x2={width - right} y1={top + (machine + 1) * lane - 10} y2={top + (machine + 1) * lane - 10} className="chart-grid" /></g>)}
        {result.operations.map(op => {
          const job = instance.jobs.findIndex(item => item.id === op.job_id);
          const barWidth = (op.duration / horizon) * plot;
          const future = result.trace.length > 0 && op.step > replayStep;
          return <g key={op.id} role="button" tabIndex={0} aria-label={label(op)} aria-pressed={op.id === selected} onClick={() => onSelect(op.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(op.id); } }} className={`operation-bar ${op.id === selected ? 'selected' : ''} ${future ? 'future' : ''}`}>
            <title>{label(op)}</title>
            <rect x={x(op.start)} y={top + op.machine * lane} width={Math.max(barWidth, 2)} height={53} rx={3} fill={JOB_COLORS[job % JOB_COLORS.length]} />
            <rect x={x(op.start)} y={top + op.machine * lane} width={Math.max(barWidth, 2)} height={53} rx={3} fill="url(#bar-stripe)" />
            {barWidth > 47 && <text clipPath={`url(#clip-${op.id})`} x={x(op.start) + 9} y={top + op.machine * lane + 23} className="operation-name">{op.id}</text>}
            {barWidth > 67 && <text clipPath={`url(#clip-${op.id})`} x={x(op.start) + 9} y={top + op.machine * lane + 42} className="operation-time">{op.start} – {op.end}</text>}
          </g>;
        })}
        {chosen && <line x1={x(chosen.start)} x2={x(chosen.start)} y1={top - 11} y2={height - 7} className="playhead" />}
      </svg>
    </div>
    <p className="caption">Scroll horizontally when needed, or use the schedule table below.</p>
    <div className="job-legend">{instance.jobs.map((job, index) => <span key={job.id}><i style={{ background: JOB_COLORS[index % JOB_COLORS.length] }} />{job.id}</span>)}</div>
  </>;
}
