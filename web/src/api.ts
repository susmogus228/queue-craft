export class HttpError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.name = 'HttpError'; this.status = status; }
}

function errorMessage(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(item => {
    if (item && typeof item === 'object' && 'msg' in item) {
      const error = item as { loc?: unknown[]; msg: string };
      return `${error.loc?.filter(part => part !== 'body').join(' → ') ?? 'Input'}: ${error.msg}`;
    }
    return String(item);
  }).join('; ');
  return 'The server could not complete this request.';
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  const abort = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  try {
    const response = await fetch(path, { ...options, signal: controller.signal, headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
    let data: unknown;
    try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response. Check that the QueueCraft API is running.'); }
    if (!response.ok) {
      const body = data as { detail?: unknown; error?: unknown };
      throw new HttpError(errorMessage(body.detail ?? body.error ?? `Request failed (${response.status}).`), response.status);
    }
    return data as T;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw new Error('The request timed out or was interrupted. Check the local server, then retry.');
    if (error instanceof TypeError) throw new Error('Cannot reach the local API. Start the QueueCraft server, then retry.');
    throw error;
  } finally { window.clearTimeout(timeout); options.signal?.removeEventListener('abort', abort); }
}
