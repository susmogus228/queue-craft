import type { Instance, Result, Run, Trace } from './types';

export function isRunStale(run: Pick<Run, 'instance' | 'solver_seconds'> | null, instance: Instance | null, solverSeconds: number): boolean {
  return !!run && !!instance && (JSON.stringify(run.instance) !== JSON.stringify(instance) || run.solver_seconds !== solverSeconds);
}

export function recordedDecision(trace: Trace[], step: number, selected: string): Trace | undefined {
  const current = trace.find(item => item.step === step);
  return current?.candidates.some(item => item.id === selected) ? current : trace.find(item => item.chosen_id === selected);
}

export function resultDescription(result: Result): string {
  if (!result.operations.length || !result.validation.valid) return 'No valid schedule was returned for this method.';
  if (result.optimality_proven) return 'Optimality proven by the reference solver.';
  if (result.method === 'cp_sat') return 'Feasible reference schedule; optimality is not proven.';
  return 'Feasible dispatch schedule; optimality is not claimed.';
}
