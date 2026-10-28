export type Method = 'fifo' | 'spt' | 'mwkr' | 'learned' | 'cp_sat';
export interface OperationInput { machine: number; duration: number }
export interface Job { id: string; operations: OperationInput[] }
export interface Instance { name: string; machines: number; jobs: Job[] }
export interface ScheduledOperation extends OperationInput { id: string; job_id: string; index: number; start: number; end: number; step: number }
export interface Candidate extends OperationInput { id: string; job_id: string; index: number; earliest_start: number; remaining_work: number; score: number | null; features: Record<string, number> }
export interface Trace { step: number; chosen_id: string; candidates: Candidate[] }
export interface Result { method: Method; label: string; status: string; makespan: number | null; wall_seconds: number; best_bound: number | null; optimality_proven: boolean; operations: ScheduledOperation[]; trace: Trace[]; validation: { valid: boolean; errors: string[] }; error: string | null }
export interface Run { id: string; status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'; created_at: string; elapsed_seconds: number; instance: Instance; strategies: Method[]; solver_seconds: number; results: Result[]; error: string | null }
export interface Pair { count: number; wins: number; ties: number; losses: number; mean_improvement_percent: number; mean_improvement_ci95_percent?: number[] }
export interface Evaluation { count: number; paired?: Record<string, Pair>; methods?: Record<string, { mean_makespan: number; median_wall_ms: number; valid_count: number; optimal_count: number }> }
export interface Model { ready: boolean; version?: string; feature_names?: string[]; training_summary?: Record<string, number>; evaluation?: { test?: Evaluation; ood?: Evaluation }; limitations?: string[]; error?: string }

export const METHODS: { id: Method; name: string; description: string }[] = [
  { id: 'fifo', name: 'FIFO', description: 'First in, first out' },
  { id: 'spt', name: 'SPT', description: 'Shortest processing time' },
  { id: 'mwkr', name: 'Most work remaining', description: 'Largest unfinished workload' },
  { id: 'learned', name: 'Learned policy', description: 'Trained operation scorer' },
  { id: 'cp_sat', name: 'CP-SAT', description: 'Constraint programming reference' },
];

export const JOB_COLORS = ['#80b9ef', '#dfb36f', '#b58bd6', '#81beb0', '#d7979f', '#b6c785'];

export function methodName(method: Method) { return METHODS.find(item => item.id === method)?.name ?? method; }
export function units(value: number | null | undefined) { return value == null ? '—' : Number.isInteger(value) ? String(value) : value.toFixed(2); }
export function milliseconds(seconds: number | undefined) { return seconds == null ? '—' : `${(seconds * 1000).toFixed(seconds < 0.01 ? 2 : 1)} ms`; }
