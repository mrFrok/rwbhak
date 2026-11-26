import { mockRequest } from './mock';

export const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

export class ApiError extends Error {
  code: string;
  detail: string;
  context: Record<string, unknown>;
  status?: number;
  constructor(code: string, detail = '', context?: Record<string, unknown>, status?: number) {
    super(`${code}: ${detail}`);
    this.code = code;
    this.detail = detail;
    this.context = context ?? {};
    this.status = status;
  }
}

// --- идемпотентность ---------------------------------------------------------
export const newKey = (prefix = 'ui') => `${prefix}-${Math.random().toString(36).slice(2, 14)}`;

const actionKeys = new Map<string, string>();
/** Один ключ на действие: остаётся прежним при повторных кликах и после сбоя, сбрасывается через doneAction(). */
export function actionKey(name: string): string {
  let k = actionKeys.get(name);
  if (!k) actionKeys.set(name, (k = newKey(name)));
  return k;
}
export const doneAction = (name: string) => actionKeys.delete(name);

// --- запросы -----------------------------------------------------------------
async function http<T>(method: 'GET' | 'POST', path: string, body?: unknown, key?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method === 'POST') headers['Idempotency-Key'] = key ?? newKey();
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError('UNREACHABLE', `API недоступен: ${API_BASE}`);
  }
  if (!res.ok) {
    let data: { error?: string; detail?: unknown; context?: Record<string, unknown> } = {};
    try {
      data = await res.json();
    } catch { /* тело не JSON */ }
    const code = data.error ?? (res.status === 422 ? 'VALIDATION' : `HTTP_${res.status}`);
    throw new ApiError(code, typeof data.detail === 'string' ? data.detail : '', data.context, res.status);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string, mock: boolean): Promise<T> {
  return mock ? (mockRequest('GET', path) as T) : http<T>('GET', path);
}
export async function apiPost<T>(path: string, body: unknown, mock: boolean, key?: string): Promise<T> {
  return mock ? (mockRequest('POST', path, body) as T) : http<T>('POST', path, body, key);
}

// --- тексты ошибок -----------------------------------------------------------
const ERROR_TEXT: Record<string, string> = {
  CAPACITY: 'Нет места в подсобке',
  BAD_TRANSITION: 'Это действие сейчас недоступно',
  SIZE_NOT_ALLOWED: 'Такой габарит идёт через хаб',
  UNREACHABLE: 'Не удаётся связаться с API',
  MOCK_MISSING: 'Для этого действия пока нет заглушки',
  VALIDATION: 'Данные заполнены неверно',
};

export function errorMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return 'Что-то пошло не так';
  let text = ERROR_TEXT[e.code] ?? `Ошибка ${e.code}`;
  if (e.code === 'CAPACITY' && e.context.needed_um != null) {
    text += `: нужно ${e.context.needed_um} УМ, свободно ${e.context.free_um}`;
  } else if (e.detail && (e.code === 'UNREACHABLE' || e.code === 'MOCK_MISSING' || !(e.code in ERROR_TEXT))) {
    text += `. ${e.detail}`;
  }
  return text;
}
