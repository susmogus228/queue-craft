import test from 'node:test';
import assert from 'node:assert/strict';
import { isRunStale, recordedDecision, resultDescription } from '../src/ui-state.ts';
import { HttpError, request } from '../src/api.ts';

const instance = {name:'A',machines:1,jobs:[{id:'J1',operations:[{machine:0,duration:1}]}]};

test('a solver-budget edit invalidates the visible run without editing the jobs', () => {
  const run = {instance,solver_seconds:2};
  assert.equal(isRunStale(run, instance, 2), false);
  assert.equal(isRunStale(run, instance, 1), true);
  assert.equal(isRunStale(run, {...instance,name:'B'}, 2), true);
});

test('a selected old operation keeps the recorded decision step explicit', () => {
  const trace = [{step:1,chosen_id:'A',candidates:[{id:'A'}]}, {step:2,chosen_id:'B',candidates:[{id:'B'}]}];
  assert.equal(recordedDecision(trace, 2, 'A').step, 1);
  assert.equal(recordedDecision(trace, 2, 'B').step, 2);
});

test('unavailable/cancelled results do not claim a feasible schedule', () => {
  for (const status of ['UNAVAILABLE','ERROR','CANCELLED','UNKNOWN']) {
    assert.match(resultDescription({status,operations:[],validation:{valid:false}}), /no valid schedule/i);
  }
  assert.match(resultDescription({operations:[{}],validation:{valid:true},optimality_proven:true}), /optimality proven/i);
});

test('HTTP failures preserve their status for unavailable-run recovery', async () => {
  const savedFetch = globalThis.fetch;
  const savedWindow = globalThis.window;
  globalThis.window = globalThis;
  globalThis.fetch = async () => new Response(JSON.stringify({detail:'Run not found or expired'}),{status:404});
  try { await assert.rejects(request('/api/runs/missing'), error => error instanceof HttpError && error.status===404); }
  finally {globalThis.fetch=savedFetch;globalThis.window=savedWindow;}
});
