import type { Instance } from './types';

function object(value: unknown, where: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${where} must be an object.`);
  return value as Record<string, unknown>;
}
function keys(value: Record<string, unknown>, allowed: string[], where: string) {
  const unknown = Object.keys(value).find(key => !allowed.includes(key));
  if (unknown) throw new Error(`${where}: unknown field "${unknown}".`);
}
function integer(value: unknown, low: number, high: number, where: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < low || value > high) throw new Error(`${where} must be an integer from ${low} to ${high}.`);
  return value;
}
export function parseInstance(value: unknown): Instance {
  const root = object(value, 'Problem'); keys(root, ['name', 'machines', 'jobs'], 'Problem');
  if (typeof root.name !== 'string' || root.name.trim().length < 1 || root.name.trim().length > 80) throw new Error('Problem name must contain 1 to 80 characters.');
  const machines = integer(root.machines, 1, 12, 'Machine count');
  if (!Array.isArray(root.jobs) || root.jobs.length < 1 || root.jobs.length > 24) throw new Error('Problem needs 1 to 24 jobs.');
  const ids = new Set<string>(); let total = 0;
  const jobs = root.jobs.map((value, index) => {
    const job = object(value, `Job ${index + 1}`); keys(job, ['id', 'operations'], `Job ${index + 1}`);
    if (typeof job.id !== 'string' || !/^[A-Za-z0-9_-]{1,24}$/.test(job.id)) throw new Error(`Job ${index + 1} ID must contain 1 to 24 letters, digits, underscores or hyphens.`);
    if (ids.has(job.id)) throw new Error('Job IDs must be unique.'); ids.add(job.id);
    if (!Array.isArray(job.operations) || job.operations.length < 1 || job.operations.length > 12) throw new Error(`${job.id} needs 1 to 12 operations.`);
    const id = job.id;
    const operations = job.operations.map((value, i) => {
      const where = `${id}, operation ${i + 1}`; const op = object(value, where); keys(op, ['machine', 'duration'], where);
      return { machine: integer(op.machine, 0, machines - 1, `${where} machine`), duration: integer(op.duration, 1, 1000, `${where} duration`) };
    }); total += operations.length;
    return { id, operations };
  });
  if (total > 144) throw new Error('A problem can contain at most 144 operations.');
  return { name: root.name.trim(), machines, jobs };
}
export function parseImportedJson(text: string): Instance {
  let value: unknown;
  try { value = JSON.parse(text); } catch { throw new Error('Choose a file containing valid JSON.'); }
  // JSON.parse discards duplicate keys. Inspect the original tokens so an
  // ambiguous import cannot silently change an operation or problem name.
  const stack: { object: boolean; key: boolean; names: Set<string> }[] = [];
  for (const token of text.match(/"(?:\\.|[^"\\])*"|[{}\[\],:]/g) ?? []) {
    if (token === '{' || token === '[') {
      stack.push({ object: token === '{', key: token === '{', names: new Set() });
    } else if (token === '}' || token === ']') {
      stack.pop();
    } else if (token === ',') {
      const frame = stack.at(-1); if (frame?.object) frame.key = true;
    } else if (token.startsWith('"')) {
      const frame = stack.at(-1);
      if (frame?.object && frame.key) {
        const name = JSON.parse(token) as string;
        if (frame.names.has(name)) throw new Error(`Duplicate JSON field "${name}". Keep one value for each field.`);
        frame.names.add(name); frame.key = false;
      }
    }
  }
  if (value && typeof value === 'object' && 'run' in value) {
    const run = (value as { run: unknown }).run;
    if (run && typeof run === 'object' && 'instance' in run && 'results' in run) value = run;
  }
  if (value && typeof value === 'object' && 'instance' in value && 'results' in value) value = (value as { instance: unknown }).instance;
  return parseInstance(value);
}
