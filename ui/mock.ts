// Заглушки: те же JSON, что в контракте. Режим включается переключателем в боковой панели.
import params from '../mock/params.json';
import pvz from '../mock/pvz.json';
import compare from '../mock/compare.json';
import scenarios from '../mock/scenarios.json';
import sensitivity from '../mock/sensitivity.json';
import mutualMap from '../mock/map.json';
import analyticsPvz from '../mock/analytics_pvz.json';
import analyticsSeller from '../mock/analytics_seller.json';
import orderB from '../mock/order_B.json';
import orderC from '../mock/order_C.json';
import stock from '../mock/stock.json';
import { ApiError } from './client';
import type { Tornado } from './types';

export const samples = { orderB, orderC };

const T0 = Date.UTC(2026, 10, 25, 8, 0, 0); // 2026-11-25T08:00 — 96 ч дают 2026-11-29T08:00, как в контракте
let nowH = 0;

const ROUTES: [RegExp, unknown][] = [
  [/^\/params$/, params],
  [/^\/pvz$/, pvz],
  [/^\/pvz\/\d+\/stock$/, stock],
  [/^\/compare$/, compare],
  [/^\/model\/scenarios$/, scenarios],
  [/^\/model\/sensitivity$/, sensitivity],
  [/^\/model\/map$/, mutualMap],
  [/^\/analytics\/pvz\/\d+$/, analyticsPvz],
  [/^\/analytics\/seller\/\d+$/, analyticsSeller],
  [/^\/orders\/\d+$/, orderB],
];

function advance(hours: number) {
  nowH += hours;
  return { now_h: nowH, now_iso: new Date(T0 + nowH * 3_600_000).toISOString().slice(0, 19) };
}

type Pt = [number, number];
function piecewise(x: number, [p0, p1, p2]: [Pt, Pt, Pt]) {
  const [[xa, ya], [xb, yb]] = x <= p1[0] ? [p0, p1] : [p1, p2];
  return ya + ((yb - ya) * (x - xa)) / (xb - xa);
}

// Приближение для режима заглушек: складываем отклонения из tornado по каждому параметру.
// Настоящий пересчёт делает POST /simulate на backend.
function simulate(body: { overrides?: Record<string, number> }) {
  const overrides = body.overrides ?? {};
  const baseParams = Object.fromEntries(params.map((p) => [p.name, p.value as number]));
  const base = compare.mesh_with_along;
  const deltaFor = (t: Tornado) => {
    let total = 0;
    for (const [name, value] of Object.entries(overrides)) {
      const row = t.rows.find((r) => r.param === name);
      const b = baseParams[name];
      if (!row || !b) continue;
      const rel = value / b - 1;
      total += piecewise(rel, [[-t.delta, row.low - t.base], [0, 0], [t.delta, row.high - t.base]]);
    }
    return total;
  };
  const dMp = deltaFor(sensitivity.tornado_marketplace as Tornado);
  const dPvz = deltaFor(sensitivity.tornado_pvz as Tornado);
  return {
    saving_month: base.saving_month + dMp,
    net_after_fixed_month: base.net_after_fixed_month + dMp,
    pvz_per_pvz_month: base.pvz_per_pvz_month + dPvz,
    approx: true,
  };
}

export function mockRequest(method: 'GET' | 'POST', path: string, body?: unknown): unknown {
  if (method === 'POST' && path === '/time/advance') return advance(Number((body as { hours?: number })?.hours ?? 0));
  if (method === 'POST' && path === '/simulate') return simulate((body ?? {}) as { overrides?: Record<string, number> });
  if (method === 'GET') {
    for (const [re, data] of ROUTES) if (re.test(path)) return structuredClone(data);
  }
  throw new ApiError('MOCK_MISSING', `Для ${method} ${path} пока нет заглушки`, undefined, 404);
}
