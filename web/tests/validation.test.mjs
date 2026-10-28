import test from 'node:test';
import assert from 'node:assert/strict';
import { parseInstance, parseImportedJson } from '../src/validation.ts';

const example = () => ({ name: 'Workshop', machines: 2, jobs: [
  { id: 'J1', operations: [{ machine: 0, duration: 3 }, { machine: 1, duration: 2 }] },
  { id: 'J2', operations: [{ machine: 1, duration: 4 }] },
] });

test('valid static problem and report import roundtrip preserve the instance', () => {
  const data = example();
  assert.deepEqual(parseInstance(data), data);
  assert.deepEqual(parseImportedJson(JSON.stringify({ id: 'run1', instance: data, results: [] })), data);
});

test('imports the actual API export envelope without accepting its metadata as problem fields', () => {
  const data = example();
  const exported = { schema_version: '1.0', exported_at: '2026-10-28T00:00:00Z', model: {ready: true}, run: {id: 'run1', instance: data, results: []} };
  assert.deepEqual(parseImportedJson(JSON.stringify(exported)), data);
});

test('rejects duplicate keys in raw JSON, including escaped spellings and nested operations', () => {
  const valid = JSON.stringify(example());
  assert.throws(() => parseImportedJson(valid.replace('"name":"Workshop"', '"name":"First","name":"Workshop"')), /duplicate/i);
  assert.throws(() => parseImportedJson(valid.replace('"duration":3', '"duration":1,"duration":3')), /duplicate/i);
  assert.throws(() => parseImportedJson(valid.replace('"name":"Workshop"', '"name":"First","\\u006eame":"Workshop"')), /duplicate/i);
  const braces = example(); braces.name = 'Escaped "quotes", braces {}, and [arrays]';
  assert.deepEqual(parseImportedJson(JSON.stringify(braces)), braces);
});

test('rejects boolean/fractional/nonpositive durations with the operation location', () => {
  for (const value of [true, 0, -1, 1.5, 1001]) {
    const data = example(); data.jobs[0].operations[0].duration = value;
    assert.throws(() => parseInstance(data), /J1.*operation 1.*duration/i);
  }
});

test('rejects invalid machine indices and duplicate IDs', () => {
  const machine = example(); machine.jobs[1].operations[0].machine = 2;
  assert.throws(() => parseInstance(machine), /machine/i);
  const duplicates = example(); duplicates.jobs[1].id = 'J1';
  assert.throws(() => parseInstance(duplicates), /unique/i);
});

test('rejects unknown fields at every schema level', () => {
  const extraRoot = { ...example(), deadline: 5 };
  assert.throws(() => parseInstance(extraRoot), /unknown.*deadline/i);
  const extraOperation = example(); extraOperation.jobs[0].operations[0].setup = 10;
  assert.throws(() => parseInstance(extraOperation), /unknown.*setup/i);
});

test('handles malformed JSON and unsafe identifiers without accepting a partial import', () => {
  assert.throws(() => parseImportedJson('{'), /valid JSON/i);
  const invalid = example(); invalid.jobs[0].id = '<script>';
  assert.throws(() => parseInstance(invalid), /ID/i);
});

test('enforces aggregate operation budget and nonempty jobs', () => {
  const large = { name: 'Large', machines: 1, jobs: Array.from({length: 13}, (_, i) => ({ id: `J${i}`, operations: Array.from({length: 12}, () => ({machine: 0, duration: 1})) })) };
  assert.throws(() => parseInstance(large), /144/);
  const empty = example(); empty.jobs[0].operations = [];
  assert.throws(() => parseInstance(empty), /1.*12.*operations/i);
});
