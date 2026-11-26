import { useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Flex, Input, Row, Segmented, Skeleton, Slider, Statistic, Table, Typography, theme } from 'antd';
import { useMutation } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { apiPost } from '../api/client';
import { useGet } from '../api/hooks';
import type { Compare, MutualMap, Param, Scenarios, Sensitivity, SchemeMetrics, SimOverrides, SimResult } from '../api/types';
import { AssumptionNote } from '../components/AssumptionNote';
import { ErrorBox } from '../components/ErrorBox';
import { Heatmap } from '../components/Heatmap';
import { Tornado } from '../components/Tornado';
import { formatHours, formatNum, formatPct, formatRub, MINUS } from '../lib/format';
import { useSettings } from '../state/settings';

const GRAY = '#808080', RED = '#d9534f', GREEN = '#2e8b57', BLUE = '#4a78a8', ORANGE = '#f58a1f';

const FUNNEL: [string, string, string][] = [ // ключ, подпись, цвет — сверху вниз
  ['mode_A', 'Выдача с полки (A)', '#2e8b57'],
  ['mode_B_along', 'Рейс: попутный (B)', '#6db98a'],
  ['mode_B_dedicated', 'Рейс: выделенный (B)', '#a1d39c'],
  ['trip_cost', 'Хаб: рейс не окупается', '#f5d155'],
  ['time', 'Хаб: срок хуже', '#eea25c'],
  ['size', 'Хаб: габарит L/КГТ', '#d9534f'],
  ['distance', 'Хаб: дальний заказ', '#808080'],
  ['zone', 'Хаб: низкая плотность', '#9b7fc4'],
  ['capacity', 'Хаб: нет места в ПВЗ', '#5aa9c9'],
  ['unprofitable', 'Хаб: невыгодно по цене', '#b0b0b0'],
];

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);
const fmtSep = (v: number) => formatNum(v, Number.isInteger(v) ? 0 : 1);

function Section({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <section style={{ marginTop: 40 }}>
      <Typography.Title level={3} style={{ marginBottom: note ? 4 : 16 }}>{title}</Typography.Title>
      {note && <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>{note}</Typography.Paragraph>}
      {children}
    </section>
  );
}

function showValue(v: unknown): string {
  if (typeof v === 'boolean') return v ? 'да' : 'нет';
  if (Array.isArray(v)) return v.join(', ');
  if (typeof v === 'number') return formatNum(v, Number.isInteger(v) ? 0 : 2);
  return String(v ?? '');
}

export default function ModelPage() {
  const { token } = theme.useToken();
  const compareQ = useGet<Compare>('/compare');
  const scenQ = useGet<Scenarios>('/model/scenarios');
  const sensQ = useGet<Sensitivity>('/model/sensitivity');
  const mapQ = useGet<MutualMap>('/model/map');
  const paramsQ = useGet<Param[]>('/params');

  const firstError = compareQ.error ?? scenQ.error ?? sensQ.error ?? mapQ.error ?? paramsQ.error;
  if (firstError) return <ErrorBox error={firstError} />;
  if (!compareQ.data || !scenQ.data || !sensQ.data || !mapQ.data || !paramsQ.data) return <Skeleton active paragraph={{ rows: 12 }} />;

  return <ModelContent compare={compareQ.data} scen={scenQ.data} sens={sensQ.data} map={mapQ.data} params={paramsQ.data} text={token.colorTextSecondary} grid={token.colorBorderSecondary} />;
}

interface ContentProps { compare: Compare; scen: Scenarios; sens: Sensitivity; map: MutualMap; params: Param[]; text: string; grid: string }

function ModelContent({ compare, scen, sens, map, params, text, grid }: ContentProps) {
  const ded = compare.mesh_dedicated_only;
  const along = compare.mesh_with_along;
  const reg = useMemo(() => Object.fromEntries(params.map((p) => [p.name, p.value])) as Record<string, number>, [params]);
  const axis = { tick: { fill: text, fontSize: 12 }, stroke: grid };

  return (
    <div>
      <Typography.Title level={2} style={{ marginTop: 0 }}>Модель: mesh против схемы через хаб</Typography.Title>
      <Typography.Paragraph type="secondary">
        Сравнение на одном наборе синтетических заказов. Все числа приходят из API, здесь они только показываются.
      </Typography.Paragraph>

      {/* Сводка */}
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}><Card><Statistic title="Экономия маркетплейса в месяц" value={formatRub(along.saving_month)} /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="Экономия к базе" value={formatPct(along.saving_pct)} /></Card></Col>
        <Col xs={12} lg={6}>
          <Card>
            <Statistic title="Срок ближнего заказа" value={formatHours(along.eta_mesh_h)} />
            <Typography.Text type="secondary">через хаб: {formatHours(along.eta_base_h, 0)}</Typography.Text>
          </Card>
        </Col>
        <Col xs={12} lg={6}><Card><Statistic title="Вклад ПВЗ на точку в месяц" value={formatRub(along.pvz_per_pvz_month)} /></Card></Col>
      </Row>
      <div style={{ marginTop: 8 }}><AssumptionNote>схема mesh с попутными рейсами; суммы посчитаны на допущениях команды, это не тарифы RWB.</AssumptionNote></div>

      <Comparison ded={ded} along={along} text={text} grid={grid} axis={axis} />
      <Funnel compare={compare} text={text} grid={grid} />
      <ScenarioBlock scen={scen} axis={axis} grid={grid} text={text} />

      <TornadoBlock sens={sens} text={text} grid={grid} />

      <Section title="Зона взаимной выгоды" note="Где ставки ПВЗ и плотность заказов дают выигрыш всем сторонам.">
        <Heatmap map={map} baseX={reg.pvz_fee_scale ?? 1} baseY={reg.orders_per_day ?? 100} text={text} />
      </Section>

      <Simulator reg={reg} along={along} />
      <Assumptions params={params} />
    </div>
  );
}

// --- Сравнение схем ----------------------------------------------------------
function Comparison({ ded, along, text, grid, axis }: { ded: SchemeMetrics; along: SchemeMetrics; text: string; grid: string; axis: object }) {
  const rows = [
    { key: 'hub', scheme: 'Хаб', cost: formatRub(along.base_per_order), saving: '—', pct: '—', net: '—', share: '—', eta: formatHours(along.eta_base_h), pvz: formatRub(0) },
    { key: 'ded', scheme: 'Mesh (выделенные)', cost: formatRub(ded.mesh_per_order), saving: formatRub(ded.saving_month), pct: formatPct(ded.saving_pct), net: formatRub(ded.net_after_fixed_month), share: formatPct(ded.mesh_share_pct), eta: formatHours(ded.eta_mesh_h), pvz: formatRub(ded.pvz_per_pvz_month) },
    { key: 'along', scheme: 'Mesh (+ попутные)', cost: formatRub(along.mesh_per_order), saving: formatRub(along.saving_month), pct: formatPct(along.saving_pct), net: formatRub(along.net_after_fixed_month), share: formatPct(along.mesh_share_pct), eta: formatHours(along.eta_mesh_h), pvz: formatRub(along.pvz_per_pvz_month) },
  ];
  const charts: { title: string; values: number[]; dec: number }[] = [
    { title: 'Себестоимость заказа, ₽', values: [along.base_per_order, ded.mesh_per_order, along.mesh_per_order], dec: 0 },
    { title: 'Срок ближнего заказа, ч', values: [along.eta_base_h, ded.eta_mesh_h, along.eta_mesh_h], dec: 0 },
    { title: 'Вклад ПВЗ, ₽ в месяц на точку', values: [0, ded.pvz_per_pvz_month, along.pvz_per_pvz_month], dec: 0 },
  ];
  const names = ['Хаб', 'Mesh (выд.)', 'Mesh (+поп.)'];
  const colors = [GRAY, RED, GREEN];
  return (
    <Section title="Сравнение схем">
      <Table
        size="small" pagination={false} rowKey="key" dataSource={rows} scroll={{ x: 900 }}
        columns={[
          { title: 'Схема', dataIndex: 'scheme', fixed: 'left' },
          { title: 'Себестоимость заказа', dataIndex: 'cost', align: 'right' },
          { title: 'Экономия в месяц', dataIndex: 'saving', align: 'right' },
          { title: 'Экономия к базе', dataIndex: 'pct', align: 'right' },
          { title: 'После постоянных расходов', dataIndex: 'net', align: 'right' },
          { title: 'Доля mesh в заказах', dataIndex: 'share', align: 'right' },
          { title: 'Срок ближнего заказа', dataIndex: 'eta', align: 'right' },
          { title: 'Вклад ПВЗ на точку в месяц', dataIndex: 'pvz', align: 'right' },
        ]}
      />
      {ded.net_after_fixed_month < 0 && (
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
          Схема только с выделенными рейсами не покрывает постоянные расходы пилота: колонка «После постоянных расходов» отрицательная.
        </Typography.Paragraph>
      )}
      <Row gutter={16} style={{ marginTop: 16 }}>
        {charts.map((c) => (
          <Col xs={24} md={8} key={c.title}>
            <Typography.Text strong>{c.title}</Typography.Text>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={names.map((n, i) => ({ n, v: c.values[i] }))} margin={{ top: 22, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={grid} vertical={false} />
                <XAxis dataKey="n" {...axis} />
                <YAxis {...axis} width={48} tickFormatter={fmtSep} />
                <Tooltip formatter={(v: number) => formatNum(v, c.dec)} cursor={{ fill: 'rgba(128,128,128,.12)' }} />
                <Bar dataKey="v" name={c.title}>
                  {colors.map((col) => <Cell key={col} fill={col} />)}
                  <LabelList dataKey="v" position="top" formatter={(v: number) => formatNum(v, c.dec)} fill={text} fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Col>
        ))}
      </Row>
    </Section>
  );
}

// --- Воронка -----------------------------------------------------------------
function Funnel({ compare, text, grid }: { compare: Compare; text: string; grid: string }) {
  const [scheme, setScheme] = useState<'mesh_with_along' | 'mesh_dedicated_only'>('mesh_with_along');
  const src = compare[scheme];
  const present = FUNNEL.filter(([k]) => (src.funnel[k] ?? 0) > 0);
  const hidden = FUNNEL.filter(([k]) => !((src.funnel[k] ?? 0) > 0)).map(([, l]) => `«${l}»`);
  // доля = заказы / все заказы: нормировка только для подписи, модель считается в API
  const data = present.map(([k, label, color]) => ({ label, color, count: src.funnel[k], share: (src.funnel[k] / src.orders) * 100 }));
  return (
    <Section title="Куда уходят заказы и почему">
      <Segmented
        value={scheme} onChange={(v) => setScheme(v as typeof scheme)}
        options={[{ value: 'mesh_with_along', label: 'Mesh (+ попутные)' }, { value: 'mesh_dedicated_only', label: 'Mesh (выделенные)' }]}
      />
      <ResponsiveContainer width="100%" height={40 * data.length + 50}>
        <BarChart data={data} layout="vertical" margin={{ top: 16, right: 56, left: 8, bottom: 8 }}>
          <CartesianGrid stroke={grid} horizontal={false} />
          <XAxis type="number" tick={{ fill: text, fontSize: 12 }} stroke={grid} unit="%" />
          <YAxis type="category" dataKey="label" width={190} tick={{ fill: text, fontSize: 13 }} stroke={grid} />
          <Tooltip formatter={(_: number, __: string, p) => `${formatNum(p.payload.count)} заказов`} cursor={{ fill: 'rgba(128,128,128,.12)' }} />
          <Bar dataKey="share" name="Доля заказов">
            {data.map((d) => <Cell key={d.label} fill={d.color} />)}
            <LabelList dataKey="share" position="right" formatter={(v: number) => `${formatNum(v, 1)}%`} fill={text} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <Typography.Text type="secondary">% всех заказов.{hidden.length > 0 && ` Причины без заказов скрыты: ${hidden.join(', ')}.`}</Typography.Text>
    </Section>
  );
}

// --- Сценарии ----------------------------------------------------------------
function ScenarioBlock({ scen, axis, grid, text }: { scen: Scenarios; axis: object; grid: string; text: string }) {
  const names = ['Пессимистичный', 'Базовый', 'Оптимистичный'].filter((n) => n in scen);
  const order = names.length ? names : Object.keys(scen);
  const [choice, setChoice] = useState(order.includes('Базовый') ? 'Базовый' : order[0]);
  const s = scen[choice];
  const data = order.map((n) => ({ n, saving: scen[n].saving_month, net: scen[n].net_after_fixed_month }));
  return (
    <Section title="Три сценария">
      <Segmented value={choice} onChange={(v) => setChoice(String(v))} options={order} />
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {[
          ['Экономия в месяц', formatRub(s.saving_month)],
          ['После постоянных расходов', formatRub(s.net_after_fixed_month)],
          ['Доля mesh', formatPct(s.mesh_share_pct)],
          ['Срок ближнего заказа', formatHours(s.eta_mesh_h)],
          ['Вклад ПВЗ на точку', formatRub(s.pvz_per_pvz_month)],
          ['Зона плотности', s.zone ?? '—'],
        ].map(([t, v]) => (
          <Col xs={12} md={8} xl={4} key={t}><Statistic title={t} value={v} /></Col>
        ))}
      </Row>
      {s.net_after_fixed_month < 0 && (
        <Alert style={{ marginTop: 16 }} type="warning" showIcon message="В этом сценарии экономии не хватает на покрытие постоянных расходов пилота." />
      )}
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 24, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="n" {...axis} />
          <YAxis {...axis} width={64} tickFormatter={fmtSep} label={{ value: '₽ в месяц', angle: -90, position: 'insideLeft', fill: text }} />
          <Tooltip formatter={(v: number) => formatRub(v)} cursor={{ fill: 'rgba(128,128,128,.12)' }} />
          <Legend />
          <Bar dataKey="saving" name="Экономия" fill={GREEN}>{data.map((d) => <Cell key={d.n} fill={GREEN} fillOpacity={d.n === choice ? 1 : 0.4} />)}</Bar>
          <Bar dataKey="net" name="После постоянных расходов" fill={BLUE}>{data.map((d) => <Cell key={d.n} fill={BLUE} fillOpacity={d.n === choice ? 1 : 0.4} />)}</Bar>
        </BarChart>
      </ResponsiveContainer>
    </Section>
  );
}

// --- Чувствительность --------------------------------------------------------
function TornadoBlock({ sens, text, grid }: { sens: Sensitivity; text: string; grid: string }) {
  const [who, setWho] = useState<'mp' | 'pvz'>('mp');
  const t = who === 'mp' ? sens.tornado_marketplace : sens.tornado_pvz;
  const label = t.metric === 'saving_month' ? 'Экономия маркетплейса, ₽ в месяц' : t.metric === 'pvz_per_pvz_month' ? 'Вклад на один ПВЗ, ₽ в месяц' : t.metric;
  const d = Math.round(t.delta * 100);
  const flat = t.rows.filter((r) => r.swing < 1).map((r) => `«${r.label}»`);
  return (
    <Section title="Чувствительность" note={`Что сильнее всего двигает результат при изменении параметра на ±${d}%.`}>
      <Segmented value={who} onChange={(v) => setWho(v as typeof who)} options={[{ value: 'mp', label: 'Маркетплейс' }, { value: 'pvz', label: 'ПВЗ' }]} />
      <div style={{ marginTop: 12 }}>
        <Tornado data={t} axisLabel={label} text={text} grid={grid} low={BLUE} high={ORANGE} />
      </div>
      <Flex gap={16} style={{ fontSize: 13 }}>
        <span><span style={{ color: BLUE }}>■</span> {MINUS}{d}%</span>
        <span><span style={{ color: ORANGE }}>■</span> +{d}%</span>
      </Flex>
      {flat.length > 0 && <Typography.Text type="secondary">Не меняют результат при ±{d}%: {flat.join(', ')}.</Typography.Text>}
    </Section>
  );
}

// --- Симулятор ---------------------------------------------------------------
function Simulator({ reg, along }: { reg: Record<string, number>; along: SchemeMetrics }) {
  const { mock } = useSettings();
  const [opd, setOpd] = useState(clamp(reg.orders_per_day ?? 100, 20, 160));
  const [tcs, setTcs] = useState(clamp(reg.trip_cost_scale ?? 1, 0.5, 2));
  const [pfs, setPfs] = useState(clamp(reg.pvz_fee_scale ?? 1, 0.5, 1.7));
  const [nbs, setNbs] = useState(clamp(reg.nearby_share ?? 0.85, 0.3, 1));
  const [used, setUsed] = useState<SimOverrides | null>(null);

  const sim = useMutation<SimResult, Error, SimOverrides>({
    mutationFn: (overrides) => apiPost<SimResult>('/simulate', { overrides }, mock), // новый ключ на каждый клик: каждый расчёт — отдельное действие
    onSuccess: (_r, v) => setUsed(v),
  });

  const METRICS: [keyof SchemeMetrics, string, (v: number | null) => string][] = [
    ['saving_month', 'Экономия в месяц', formatRub],
    ['saving_pct', 'Экономия к базе', formatPct],
    ['net_after_fixed_month', 'После постоянных расходов', formatRub],
    ['mesh_share_pct', 'Доля mesh в заказах', formatPct],
    ['eta_mesh_h', 'Срок ближнего заказа', formatHours],
    ['pvz_per_pvz_month', 'Вклад ПВЗ на точку в месяц', formatRub],
  ];
  const res = sim.data;
  const rows = res ? METRICS.filter(([k]) => res[k] != null && along[k] != null).map(([k, label, fmt]) => ({ key: k, label, base: fmt(along[k] as number), sim: fmt(res[k] as number) })) : [];

  const field = (title: string, node: React.ReactNode) => (
    <div style={{ marginBottom: 12 }}><Typography.Text>{title}</Typography.Text>{node}</div>
  );

  return (
    <Section title="Симулятор" note="Подвигайте допущения и нажмите «Пересчитать»: результат появится рядом с базой.">
      <Row gutter={[32, 16]}>
        <Col xs={24} lg={9}>
          {field(`Заказов в день: ${opd}`, <Slider min={20} max={160} step={5} value={opd} onChange={setOpd} />)}
          {field(`Стоимость рейса: ×${formatNum(tcs, 2)}`, <Slider min={0.5} max={2} step={0.05} value={tcs} onChange={setTcs} tooltip={{ formatter: (v) => `×${formatNum(v ?? 0, 2)}` }} />)}
          {field(`Ставки ПВЗ: ×${formatNum(pfs, 2)}`, <Slider min={0.5} max={1.7} step={0.05} value={pfs} onChange={setPfs} tooltip={{ formatter: (v) => `×${formatNum(v ?? 0, 2)}` }} />)}
          {field(`Доля ближних заказов: ${formatNum(nbs * 100, 0)}%`, <Slider min={0.3} max={1} step={0.05} value={nbs} onChange={setNbs} tooltip={{ formatter: (v) => `${formatNum((v ?? 0) * 100, 0)}%` }} />)}
          <Button type="primary" loading={sim.isPending} onClick={() => sim.mutate({ orders_per_day: opd, trip_cost_scale: tcs, pvz_fee_scale: pfs, nearby_share: nbs })}>
            Пересчитать
          </Button>
        </Col>
        <Col xs={24} lg={15}>
          {sim.error && <ErrorBox error={sim.error} />}
          {!res && !sim.error && <Alert type="info" showIcon message="Результата пока нет. Нажмите «Пересчитать»." />}
          {res && (
            <>
              <Table
                size="small" pagination={false} rowKey="key" dataSource={rows}
                columns={[
                  { title: 'Показатель', dataIndex: 'label' },
                  { title: 'База', dataIndex: 'base', align: 'right' },
                  { title: 'Симуляция', dataIndex: 'sim', align: 'right' },
                ]}
              />
              {used && (
                <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
                  Параметры расчёта: {used.orders_per_day} заказов в день, рейс ×{formatNum(used.trip_cost_scale, 2)}, ставки ПВЗ ×{formatNum(used.pvz_fee_scale, 2)}, ближние {formatNum(used.nearby_share * 100, 0)}%.
                  {res.approx && ' Режим заглушек: приближение по данным чувствительности, а не пересчёт модели. Точные числа даст API.'}
                </Typography.Paragraph>
              )}
            </>
          )}
        </Col>
      </Row>
    </Section>
  );
}

// --- Допущения ---------------------------------------------------------------
function Assumptions({ params }: { params: Param[] }) {
  const [q, setQ] = useState('');
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return params
      .map((p) => ({ key: p.id, id: p.id, name: p.name, value: showValue(p.value), unit: p.unit ?? '', note: p.note ?? '', kind: p.kind ?? '' }))
      .filter((r) => !needle || [r.id, r.name, r.value, r.unit, r.note, r.kind].some((s) => s.toLowerCase().includes(needle)));
  }, [params, q]);
  return (
    <Section title="Допущения" note="Все значения — допущения команды, а не тарифы RWB. Реестр отдаёт GET /params.">
      <Input.Search allowClear placeholder="Поиск: хаб, ставка, A07" onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 360, marginBottom: 12 }} />
      <Table
        size="small" rowKey="key" dataSource={rows} scroll={{ x: 800 }} pagination={{ pageSize: 15, hideOnSinglePage: true, showSizeChanger: false }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 70 },
          { title: 'Параметр', dataIndex: 'name' },
          { title: 'Значение', dataIndex: 'value', align: 'right' },
          { title: 'Ед.', dataIndex: 'unit', width: 90 },
          { title: 'Пояснение', dataIndex: 'note' },
          { title: 'Тип', dataIndex: 'kind' },
        ]}
        locale={{ emptyText: 'Ничего не найдено. Измените запрос.' }}
      />
    </Section>
  );
}
