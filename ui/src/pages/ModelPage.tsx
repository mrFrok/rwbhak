import { ExperimentOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCompare, useParams, useSimulate, useThreshold } from "../api/hooks";
import type { Compare } from "../api/types";
import { Kpi, SectionTitle, fmtRub } from "../components/ui";

export default function ModelPage() {
  const [kind, setKind] = useState<"DEDICATED" | "ALONG">("DEDICATED");
  const [orders, setOrders] = useState(3000);
  const [seed, setSeed] = useState(42);
  const compare = useCompare(kind);
  const threshold = useThreshold();
  const params = useParams();
  const simulate = useSimulate();
  const [result, setResult] = useState<Compare | null>(null);

  const data = result ?? compare.data;

  const run = () => {
    simulate.mutate(
      { orders, seed, kind, days: 30 },
      {
        onSuccess: (value) => {
          setResult(value);
          message.success("Модель пересчитана на том же потоке заказов");
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
            Две схемы на одном потоке заказов. Сравниваем устранимые затраты, долю mesh и
            порог окупаемости рейса. Все числа — допущения команды, реестр ниже.
          </p>
        </div>
        <Space wrap>
          <Select
            value={kind}
            onChange={(value) => {
              setKind(value);
              setResult(null);
            }}
            style={{ width: 190 }}
            options={[
              { value: "DEDICATED", label: "Выделенный рейс" },
              { value: "ALONG", label: "Попутная загрузка" },
            ]}
          />
          <InputNumber min={100} max={10000} step={100} value={orders} onChange={(v) => setOrders(v ?? 3000)} addonAfter="заказов" style={{ width: 190 }} />
          <InputNumber min={1} max={9999} value={seed} onChange={(v) => setSeed(v ?? 42)} addonBefore="seed" style={{ width: 150 }} />
          <Button type="primary" icon={<ExperimentOutlined aria-hidden="true" />} loading={simulate.isPending} onClick={run}>
            Пересчитать
          </Button>
        </Space>
      </div>

      {data && (
        <>
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <Card size="small">
                <Kpi label="Через хаб" value={fmtRub(data.totals.cost_per_order_hub)} hint="₽ на модельный заказ" />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Kpi label="Mesh" value={fmtRub(data.totals.cost_per_order_mesh)} hint="₽ на модельный заказ" accent="#EA580C" />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Kpi
                  label="Снижение себестоимости"
                  value={`${data.totals.saving_pct.toFixed(1)}%`}
                  hint={`${fmtRub(data.totals.saving)} на потоке`}
                  accent={data.totals.saving_pct >= 5 ? "#16A34A" : "#D97706"}
                />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Kpi
                  label="Доля заказов mesh"
                  value={`${data.mesh.share_pct.toFixed(1)}%`}
                  hint={`${data.mesh.orders} из ${data.flow_orders}, рейсов: ${data.mesh.trips}`}
                />
              </Card>
            </Col>
          </Row>

          <Card size="small">
            <SectionTitle hint="Себестоимость заказа S от числа заказов в выделенном рейсе. Горизонтальная линия — цена через хаб.">
              Порог окупаемости рейса
            </SectionTitle>
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={threshold.data?.points ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                  <XAxis dataKey="orders" type="number" domain={["dataMin", "dataMax"]} tick={{ fontSize: 12 }} label={{ value: "заказов в рейсе", position: "insideBottom", offset: -4, fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} width={64} domain={["auto", "auto"]} />
                  <ChartTooltip formatter={(value) => fmtRub(typeof value === "number" ? value : undefined)} />
                  <Legend />
                  <ReferenceLine y={threshold.data?.points[0]?.hub} stroke="#64748B" strokeDasharray="4 4" label={{ value: "хаб", fontSize: 12, position: "insideTopRight" }} />
                  <ReferenceLine x={threshold.data?.threshold} stroke="#16A34A" strokeDasharray="4 4" label={{ value: `порог ${threshold.data?.threshold ?? ""}`, fontSize: 12, position: "insideTopRight" }} />
                  <Line type="monotone" dataKey="mesh" name="Mesh, ₽/заказ" stroke="#2563EB" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="row">
            <Card size="small" className="grow" title="Что входит в сравнение">
              <Table
                size="small"
                pagination={false}
                rowKey="key"
                dataSource={[
                  { key: "flow", label: "Заказов в потоке", value: `${data.flow_orders} · ${data.orders_per_day} в день` },
                  { key: "hub", label: "Всего через хаб", value: `${data.hub.orders} (${data.hub.share_pct.toFixed(1)}%)` },
                  { key: "mesh", label: "Всего mesh", value: `${data.mesh.orders} (${data.mesh.share_pct.toFixed(1)}%)` },
                  { key: "trips", label: "Принято рейсов", value: String(data.mesh.trips) },
                  { key: "rejected", label: "Рейсов ниже порога", value: String(data.rejected_trips) },
                  { key: "cost", label: "Стоимость рейса", value: `${fmtRub(data.trip_cost)} (${data.trip_kind === "DEDICATED" ? "выделенный" : "попутный"})` },
                ]}
                columns={[
                  { title: "Показатель", dataIndex: "label" },
                  { title: "Значение", dataIndex: "value", align: "right", render: (v: string) => <span className="num">{v}</span> },
                ]}
              />
            </Card>

            <Card size="small" className="grow" title="Пороги из допущений">
              <div className="stack" style={{ gap: 8 }}>
                <div>
                  <span className="muted">Только S:</span>{" "}
                  <Tag color="blue">{data.thresholds.dedicated_s} выделенный</Tag> <Tag color="orange">{data.thresholds.along_s} попутный</Tag>
                </div>
                <div>
                  <span className="muted">Поток 70% S + 30% M:</span>{" "}
                  <Tag color="blue">{data.thresholds.dedicated_mixed} выделенный</Tag> <Tag color="orange">{data.thresholds.along_mixed} попутный</Tag>
                </div>
                <div className="muted" style={{ fontSize: 12 }}>
                  Попутная загрузка снижает порог примерно в шесть раз: сравниваем не весь рейс,
                  а приращение 750 ₽.
                </div>
              </div>
            </Card>
          </div>

          {data.pilot && (
            <Card size="small" title="Экономика пилота: 1 коридор, 4 ПВЗ, 4 рейса в неделю">
              <div className="row" style={{ marginBottom: 16 }}>
                <div>
                  <div className="kpi__label">Средняя экономия до рейса</div>
                  <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>{fmtRub(data.pilot.avg_saving)}</div>
                </div>
                <div>
                  <div className="kpi__label">Постоянные расходы</div>
                  <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>{fmtRub(data.pilot.fixed_cost_month)}/мес</div>
                </div>
                <div>
                  <div className="kpi__label">Порог окупаемости пилота</div>
                  <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>
                    <Tag color="blue">{data.pilot.breakeven_dedicated} выделенный</Tag>
                    <Tag color="orange">{data.pilot.breakeven_along} попутный</Tag>
                  </div>
                </div>
              </div>
              <Table
                size="small"
                rowKey="orders"
                pagination={false}
                dataSource={data.pilot.rows}
                columns={[
                  { title: "Заказов в рейсе", dataIndex: "orders", align: "right", render: (v: number) => <span className="num">{v}</span> },
                  {
                    title: "Выделенный, ₽/мес после пост. расходов",
                    dataIndex: "effect_dedicated",
                    align: "right",
                    render: (v: number) => <span className="num" style={{ color: v >= 0 ? "#16A34A" : "#DC2626" }}>{fmtRub(v)}</span>,
                  },
                  {
                    title: "Попутный, ₽/мес после пост. расходов",
                    dataIndex: "effect_along",
                    align: "right",
                    render: (v: number) => <span className="num" style={{ color: v >= 0 ? "#16A34A" : "#DC2626" }}>{fmtRub(v)}</span>,
                  },
                ]}
              />
              <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
                Один слабый коридор выделенным транспортом не окупает постоянные затраты;
                попутная загрузка выводит пилот в плюс уже от {data.pilot.breakeven_along} заказов в рейсе.
              </div>
            </Card>
          )}

          {data.sensitivity && data.sensitivity.length > 0 && (
            <Card size="small" title="Чувствительность: ±20% к параметрам">
              <Table
                size="small"
                rowKey={(row) => `${row.parameter}-${row.delta_pct}`}
                pagination={false}
                dataSource={data.sensitivity}
                columns={[
                  { title: "Параметр", dataIndex: "parameter" },
                  { title: "Изменение", dataIndex: "delta_pct", align: "right", render: (v: number) => `${v > 0 ? "+" : ""}${v}%` },
                  { title: "₽/заказ", dataIndex: "cost_per_order", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                  { title: "К базе", dataIndex: "saving_vs_base_pct", align: "right", render: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%` },
                ]}
              />
            </Card>
          )}
        </>
      )}

      <Card size="small" title="Реестр допущений">
        <Table
          size="small"
          rowKey="code"
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          dataSource={params.data?.assumptions ?? []}
          columns={[
            { title: "Код", dataIndex: "code", width: 200, render: (v: string) => <code>{v}</code> },
            { title: "Допущение", dataIndex: "name" },
            { title: "Значение", key: "value", width: 180, render: (_: unknown, row) => <span className="num">{`${row.value} ${row.unit}`}</span> },
            { title: "Источник", dataIndex: "source", width: 220 },
          ]}
        />
      </Card>
    </div>
  );
}
