import { ExperimentOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  InputNumber,
  Row,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useState } from "react";
import {
  useModelCompare,
  useModelMap,
  useModelParams,
  useModelScenarios,
  useModelSimulate,
  useModelTornado,
} from "../api/hooks";
import type { MutualMap, ParamRow, SchemeMetrics } from "../api/types";
import { Kpi, SectionTitle, fmtRub } from "../components/ui";

const STATUS_COLORS: Record<number, string> = {
  0: "#E2E8F0",
  1: "#FDE68A",
  2: "#86EFAC",
  3: "#15803D",
};
const STATUS_LABELS: Record<number, string> = {
  0: "mesh не включается",
  1: "ПВЗ ниже минимума",
  2: "выигрывают все",
  3: "покрыты расходы пилота",
};

export default function ModelPage() {
  const compare = useModelCompare();
  const scenarios = useModelScenarios();
  const tornado = useModelTornado();
  const map = useModelMap();
  const params = useModelParams();
  const simulate = useModelSimulate();
  const [orders, setOrders] = useState(100);
  const [tripScale, setTripScale] = useState(1);
  const [custom, setCustom] = useState<SchemeMetrics | null>(null);

  const base = compare.data?.mesh_with_along;
  const dedicated = compare.data?.mesh_dedicated_only;

  const run = () => {
    simulate.mutate(
      { orders_per_day: orders, trip_cost_scale: tripScale },
      {
        onSuccess: (value) => {
          setCustom(value);
          message.success("Модель пересчитана с новыми параметрами");
        },
        onError: (error) => message.error(error.message),
      },
    );
  };

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Модель</h1>
          <p>
            Имитационная модель коридора: одни и те же заказы проходят через хаб и через mesh,
            средние по пяти seed. Числа берутся из <code>reports/results.json</code> и
            пересчитываются кодом <code>analytic/</code>, а не вводятся руками.
          </p>
        </div>
        <Space wrap>
          <InputNumber
            min={20}
            max={200}
            step={10}
            value={orders}
            onChange={(value) => setOrders(value ?? 100)}
            addonAfter="заказов/день"
            style={{ width: 190 }}
          />
          <InputNumber
            min={0.5}
            max={2}
            step={0.05}
            value={tripScale}
            onChange={(value) => setTripScale(value ?? 1)}
            addonBefore="рейс ×"
            style={{ width: 130 }}
          />
          <Button type="primary" icon={<ExperimentOutlined aria-hidden="true" />} loading={simulate.isPending} onClick={run}>
            Пересчитать
          </Button>
        </Space>
      </div>

      {base && dedicated && (
        <>
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <Card size="small">
                <Kpi label="Через хаб" value={fmtRub(base.base_per_order)} hint="₽ на заказ по потоку" />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Kpi label="Mesh с попутными" value={fmtRub(base.mesh_per_order)} hint="₽ на заказ" accent="#C2410C" />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Kpi
                  label="Экономия маркетплейса"
                  value={`${fmtRub(base.saving_month)}/мес`}
                  hint={`${base.saving_pct.toFixed(1)}% к базе`}
                  accent={base.saving_pct >= 5 ? "#16A34A" : "#D97706"}
                />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Kpi
                  label="После постоянных расходов"
                  value={`${fmtRub(base.net_after_fixed_month)}/мес`}
                  hint="60 000 ₽/мес на пилот"
                  accent={base.net_after_fixed_month >= 0 ? "#16A34A" : "#DC2626"}
                />
              </Card>
            </Col>
          </Row>

          {custom && (
            <Alert
              type="info"
              showIcon
              message={`Пересчёт: ${orders} заказов/день, стоимость рейса × ${tripScale}`}
              description={`Экономия ${fmtRub(custom.saving_month)}/мес (${custom.saving_pct.toFixed(1)}%), после постоянных ${fmtRub(custom.net_after_fixed_month)}/мес, mesh ${custom.mesh_share_pct.toFixed(1)}%`}
            />
          )}

          <Card size="small">
            <SectionTitle hint="Сравнение на одном потоке: только выделенные рейсы и с попутной загрузкой.">
              Схемы
            </SectionTitle>
            <Table
              size="small"
              rowKey="metric"
              pagination={false}
              dataSource={[
                { metric: "Себестоимость заказа, ₽", dedicated: dedicated.mesh_per_order, along: base.mesh_per_order, raw: true },
                { metric: "Экономия, ₽/мес", dedicated: dedicated.saving_month, along: base.saving_month, raw: true },
                { metric: "Экономия, % к базе", dedicated: dedicated.saving_pct, along: base.saving_pct, raw: false },
                { metric: "После постоянных расходов, ₽/мес", dedicated: dedicated.net_after_fixed_month, along: base.net_after_fixed_month, raw: true },
                { metric: "Доля заказов через mesh, %", dedicated: dedicated.mesh_share_pct, along: base.mesh_share_pct, raw: false },
                { metric: "Срок ближнего заказа, ч", dedicated: dedicated.eta_mesh_h, along: base.eta_mesh_h, raw: false },
                { metric: "Вклад ПВЗ на точку, ₽/мес", dedicated: dedicated.pvz_per_pvz_month, along: base.pvz_per_pvz_month, raw: true },
                { metric: "Рейсов в месяц (выделенных / попутных)", dedicated: `${dedicated.trips_dedicated} / ${dedicated.trips_along}`, along: `${base.trips_dedicated} / ${base.trips_along}`, raw: true },
              ]}
              columns={[
                { title: "Показатель", dataIndex: "metric" },
                {
                  title: "Только выделенные",
                  dataIndex: "dedicated",
                  align: "right",
                  render: (value: number | string, row) =>
                    typeof value === "number" ? <span className="num">{row.raw ? fmtRub(value) : value.toFixed(1)}</span> : <span className="num">{value}</span>,
                },
                {
                  title: "+ попутная загрузка",
                  dataIndex: "along",
                  align: "right",
                  render: (value: number | string, row) =>
                    typeof value === "number" ? <span className="num">{row.raw ? fmtRub(value) : value.toFixed(1)}</span> : <span className="num">{value}</span>,
                },
              ]}
            />
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
              Зона коридора: <Tag color={base.zone === "GREEN" ? "green" : "gold"}>{base.zone}</Tag>
              λ = {base.lambda_per_day.toFixed(1)} заказов/день · заказов в прогоне: {base.orders}
            </div>
          </Card>

          <div className="row">
            <Card size="small" className="grow">
              <SectionTitle hint="Пессимистичный: рейс +25%, хаб −15%, поток −25%, ставки ПВЗ +15%. Оптимистичный — зеркально.">
                Сценарии
              </SectionTitle>
              <Table
                size="small"
                rowKey="name"
                pagination={false}
                dataSource={Object.entries(scenarios.data ?? {}).map(([name, row]) => ({ name, ...row }))}
                columns={[
                  { title: "Сценарий", dataIndex: "name" },
                  { title: "Зона", dataIndex: "zone" },
                  { title: "Экономия, ₽/мес", dataIndex: "saving_month", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                  { title: "%", dataIndex: "saving_pct", align: "right", render: (v: number) => `${v.toFixed(1)}%` },
                  { title: "После постоянных", dataIndex: "net_after_fixed_month", align: "right", render: (v: number) => <span className="num" style={{ color: v >= 0 ? "#16A34A" : "#DC2626" }}>{fmtRub(v)}</span> },
                ]}
              />
            </Card>
          </div>

          <Card size="small">
            <SectionTitle hint="Как меняется экономия при отклонении параметра на ±25%.">
              Чувствительность
            </SectionTitle>
            <Table
              size="small"
              rowKey="param"
              pagination={false}
              dataSource={tornado.data?.rows ?? []}
              columns={[
                { title: "Параметр", dataIndex: "label" },
                { title: "−25%, ₽/мес", dataIndex: "low", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                { title: "+25%, ₽/мес", dataIndex: "high", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                { title: "Размах, ₽/мес", dataIndex: "swing", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
              ]}
            />
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
              База: {fmtRub(tornado.data?.base)}/мес. Самый чувствительный параметр — {tornado.data?.rows[0]?.label.toLowerCase()}.
            </div>
          </Card>

          <Card size="small">
            <SectionTitle hint="Ось X — ставки ПВЗ к базовым, ось Y — заказов в день. Наведите на ячейку, чтобы увидеть значение.">
              Зона взаимной выгоды
            </SectionTitle>
            <MutualMapGrid map={map.data} />
            <Space wrap size={16} style={{ marginTop: 12 }}>
              {Object.entries(STATUS_LABELS).map(([code, label]) => (
                <span key={code} style={{ fontSize: 12 }}>
                  <span className="mode-dot" style={{ background: STATUS_COLORS[Number(code)], marginRight: 6 }} />
                  {label}
                </span>
              ))}
            </Space>
          </Card>
        </>
      )}

      <Card size="small">
        <SectionTitle hint="Все ставки — допущения команды, не тарифы RWB. Меняются в analytic/parameters.py.">
          Реестр допущений
        </SectionTitle>
        <Table
          size="small"
          rowKey="id"
          pagination={{ pageSize: 12, hideOnSinglePage: true }}
          dataSource={params.data ?? []}
          columns={[
            { title: "ID", dataIndex: "id", width: 70, render: (v: string) => <code>{v}</code> },
            { title: "Параметр", dataIndex: "name", width: 200, render: (v: string) => <code>{v}</code> },
            {
              title: "Значение",
              key: "value",
              width: 140,
              render: (_: unknown, row: ParamRow) => (
                <span className="num">
                  {Array.isArray(row.value)
                    ? row.value.join(", ")
                    : typeof row.value === "number" && !Number.isInteger(row.value)
                      ? row.value.toFixed(2)
                      : String(row.value)}{" "}
                  {row.unit}
                </span>
              ),
            },
            { title: "Пояснение", dataIndex: "note" },
          ]}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {params.data?.length ?? 0} параметров · источник: GET /params
        </Typography.Text>
      </Card>
    </div>
  );
}

function MutualMapGrid({ map }: { map?: MutualMap }) {
  if (!map) {
    return <div className="muted">Загрузка карты…</div>;
  }
  const rows = map.orders_per_day;
  const fees = map.pvz_fee_scale;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 11 }}>
        <tbody>
          {rows.map((opd, y) => (
            <tr key={opd}>
              <th style={{ padding: "2px 8px", textAlign: "right", color: "#52627A", fontWeight: 500 }}>{opd}</th>
              {fees.map((fee, x) => {
                const status = map.grid[y]?.[x] ?? 0;
                return (
                  <td
                    key={fee}
                    title={`${opd} заказов/день, ставки ПВЗ ×${fee}: ${STATUS_LABELS[status]}`}
                    style={{ width: 26, height: 20, background: STATUS_COLORS[status], border: "1px solid #fff" }}
                  />
                );
              })}
            </tr>
          ))}
          <tr>
            <th />
            {fees.map((fee) => (
              <th key={fee} style={{ padding: "4px 2px", color: "#52627A", fontWeight: 500 }}>{fee}</th>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
