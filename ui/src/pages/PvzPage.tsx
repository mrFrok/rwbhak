import {
  CloseCircleOutlined,
  InboxOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  useAlerts,
  useCreateOrder,
  useLedger,
  useOrderAction,
  useOrders,
  usePlanTrip,
  usePvzAnalytics,
  usePvzList,
  useReceiveBatch,
  useSkus,
  useStock,
  useTripAction,
  useTrips,
} from "../api/hooks";
import type { Order, Pvz, Sku, Trip } from "../api/types";
import {
  DecisionCard,
  DecisionDrawer,
  Kpi,
  ModeTag,
  SectionTitle,
  StatusTag,
  fmtRub,
} from "../components/ui";

export default function PvzPage() {
  const pvzList = usePvzList();
  const [pvzId, setPvzId] = useState<number>();

  useEffect(() => {
    if (pvzId === undefined && pvzList.data?.length) setPvzId(pvzList.data[0].id);
  }, [pvzList.data, pvzId]);

  const pvz = pvzList.data?.find((item) => item.id === pvzId);

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Пункт выдачи</h1>
          <p>
            Приёмка, остатки, заказы и деньги точки. Решение по каждому заказу объяснено
            фильтрами, а не спрятано в чёрном ящике.
          </p>
        </div>
        <Space wrap>
          <Select
            style={{ width: 240 }}
            value={pvzId}
            onChange={setPvzId}
            placeholder="Выберите ПВЗ"
            options={(pvzList.data ?? []).map((item) => ({
              value: item.id,
              label: `${item.name} · ${item.city}`,
            }))}
          />
        </Space>
      </div>

      {pvz && (
        <Card size="small" styles={{ body: { padding: "12px 20px" } }}>
          <Space wrap split={<span className="muted">|</span>}>
            <span>{pvz.address}</span>
            <span className="muted">Ёмкость {pvz.capacity_um} УМ, резерв {pvz.reserve_pct}%</span>
            <span className="muted">Тихие окна {pvz.quiet_windows}</span>
          </Space>
        </Card>
      )}

      <Tabs
        defaultActiveKey="stock"
        items={[
          { key: "stock", label: "Склад", children: <StockTab pvzId={pvzId} /> },
          { key: "intake", label: "Приёмка", children: <IntakeTab pvzId={pvzId} /> },
          { key: "orders", label: "Заказы", children: <OrdersTab pvzId={pvzId} /> },
          { key: "trips", label: "Рейсы", children: <TripsTab pvzId={pvzId} /> },
          { key: "analytics", label: "Аналитика", children: <AnalyticsTab pvzId={pvzId} /> },
        ]}
      />
    </div>
  );
}

function StockTab({ pvzId }: { pvzId?: number }) {
  const stock = useStock(pvzId);
  const alerts = useAlerts(pvzId);
  const data = stock.data;

  return (
    <div className="stack">
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Kpi label="Единиц на полке" value={data ? String(data.units) : "—"} hint="свободный остаток" />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Kpi label="Свободно места" value={data ? `${data.free_um} УМ` : "—"} hint={`из ${data?.pvz.available_um ?? 0} доступных`} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Kpi label="Загрузка точки" value={data ? `${data.load_pct}%` : "—"} hint="остаток и место под входящий рейс" />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Kpi
              label="Алерты неликвида"
              value={alerts.data ? String(alerts.data.length) : "—"}
              accent={alerts.data?.length ? "#D97706" : "#16A34A"}
              hint="7 и 15 дней без продаж"
            />
          </Card>
        </Col>
      </Row>

      {alerts.data && alerts.data.length > 0 && (
        <Space direction="vertical" style={{ width: "100%" }}>
          {alerts.data.map((alert) => (
            <Alert
              key={`${alert.batch_id}-${alert.type}`}
              type={alert.type === "REMOVAL_D15" ? "error" : "warning"}
              showIcon
              message={`${alert.sku}: ${alert.age_days} дн. без движения`}
              description={alert.note}
            />
          ))}
        </Space>
      )}

      <Card size="small" title="Партии на полке">
        <Table
          size="small"
          rowKey="id"
          loading={stock.isLoading}
          dataSource={data?.batches ?? []}
          pagination={false}
          scroll={{ x: 720 }}
          columns={[
            { title: "SKU", dataIndex: "sku", key: "sku" },
            { title: "Класс", dataIndex: "size_class", key: "size", width: 80 },
            { title: "УМ", dataIndex: "um", key: "um", width: 70 },
            { title: "Всего", dataIndex: "qty", key: "qty", width: 90 },
            { title: "Свободно", dataIndex: "qty_free", key: "free", width: 100 },
            {
              title: "Принято",
              dataIndex: "received_at",
              key: "received",
              width: 160,
              render: (value: string) => value.slice(0, 10),
            },
            {
              title: "Проверка",
              key: "check",
              width: 140,
              render: (_: unknown, row) =>
                row.declared_class === row.actual_class ? (
                  <Tag color="green">класс совпал</Tag>
                ) : (
                  <Tag color="red">пересорт</Tag>
                ),
            },
          ]}
        />
      </Card>
    </div>
  );
}

type IntakeInput = { sku_id: number; qty: number; declared_class: string; actual_class?: string };

function IntakeTab({ pvzId }: { pvzId?: number }) {
  const skus = useSkus();
  const stock = useStock(pvzId);
  const receive = useReceiveBatch();
  const [form] = Form.useForm<IntakeInput>();
  const [last, setLast] = useState<Record<string, unknown> | null>(null);

  const onFinish = (values: IntakeInput) => {
    if (!pvzId) return;
    receive.mutate(
      { ...values, pvz_id: pvzId },
      {
        onSuccess: (result) => {
          setLast(result);
          message.success("Партия принята, начисление записано в ledger");
          form.setFieldValue("qty", 1);
        },
        onError: (error) => message.error(error.message),
      },
    );
  };

  return (
    <div className="row">
      <Card size="small" className="grow" title="Новая партия">
        <Form
          form={form}
          layout="vertical"
          initialValues={{ qty: 1, declared_class: "S" }}
          onFinish={onFinish}
          style={{ maxWidth: 520 }}
        >
          <Form.Item name="sku_id" label="SKU" rules={[{ required: true, message: "Выберите SKU" }]}>
            <Select
              showSearch
              placeholder="Товар продавца"
              optionFilterProp="label"
              onChange={(id) => {
                const size = skus.data?.find((sku) => sku.id === id)?.size_class;
                form.setFieldsValue({ declared_class: size, actual_class: size });
              }}
              options={(skus.data ?? []).map((sku) => ({
                value: sku.id,
                label: `${sku.name} · ${sku.size_class} · ${fmtRub(sku.price)}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="qty" label="Количество единиц" rules={[{ required: true }]}>
            <InputNumber min={1} max={500} style={{ width: 180 }} />
          </Form.Item>
          <Form.Item name="declared_class" label="Заявленный класс">
            <Select
              style={{ width: 180 }}
              options={[
                { value: "S", label: "S · 1 УМ" },
                { value: "M", label: "M · 3 УМ" },
                { value: "L", label: "L · 8 УМ" },
              ]}
            />
          </Form.Item>
          <Form.Item name="actual_class" label="Фактический класс">
            <Select
              style={{ width: 180 }}
              options={["S", "M", "L"].map((size) => ({ value: size, label: size }))}
            />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="Приёмку оплачивает маркетплейс: 10 ₽ × k_оп за единицу."
            description={`Свободно ${stock.data?.space_free_um ?? "—"} УМ. При нехватке места приёмка блокируется.`}
          />
          <Button type="primary" htmlType="submit" icon={<InboxOutlined aria-hidden="true" />} loading={receive.isPending}>
            Принять партию
          </Button>
        </Form>
      </Card>
      <Card size="small" className="grow" title="Результат приёмки">
        {last ? (
          <Descriptions column={1} size="small">
            <Descriptions.Item label="Партия">#{String(last.id)}</Descriptions.Item>
            <Descriptions.Item label="Единиц">{String(last.qty)}</Descriptions.Item>
            <Descriptions.Item label="Занято">{String(last.um_total)} УМ</Descriptions.Item>
            <Descriptions.Item label="Выплата ПВЗ">{fmtRub(Number(last.acceptance_payout))}</Descriptions.Item>
            <Descriptions.Item label="Осталось места">
              {String(last.space_free_after_um)} УМ
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="Примите партию, чтобы увидеть расчёт" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
    </div>
  );
}

function OrdersTab({ pvzId }: { pvzId?: number }) {
  const pvzList = usePvzList();
  const orders = useOrders(pvzId);
  const action = useOrderAction();
  const [decisionOrder, setDecisionOrder] = useState<Order | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [ledgerOrder, setLedgerOrder] = useState<Order | null>(null);

  const run = (order: Order, act: string, label: string) => {
    action.mutate(
      { orderId: order.id, action: act },
      {
        onSuccess: () => message.success(`${label}: заказ #${order.id}`),
        onError: (error) => message.error(error.message),
      },
    );
  };

  const buttons = (order: Order) => {
    const items = [];
    if (order.status === "RESERVED") {
      items.push(
        <Button size="small" key="pick" onClick={() => run(order, "pick", "Собран")}>
          Собрать
        </Button>,
      );
    }
    const canIssue =
      (order.mode === "A" && ["RESERVED", "PICKED"].includes(order.status)) ||
      (order.mode === "B" && order.status === "ARRIVED") ||
      (order.mode === "C" && ["ROUTED_HUB", "PICKED"].includes(order.status));
    if (canIssue) {
      items.push(
        <Button size="small" type="primary" key="issue" onClick={() => run(order, "issue", "Выдан")}>
          Выдать
        </Button>,
      );
    }
    if (order.status === "ISSUED") {
      items.push(
        <Button size="small" key="return" onClick={() => run(order, "return", "Возврат запрошен")}>
          Возврат
        </Button>,
      );
    }
    if (order.status === "RETURN_REQUESTED") {
      items.push(
        <Button size="small" key="transit" onClick={() => run(order, "return/transit", "Возврат в пути")}>
          В путь
        </Button>,
      );
    }
    if (order.status === "RETURN_IN_TRANSIT") {
      items.push(
        <Button size="small" key="accept" onClick={() => run(order, "return/accept", "Возврат принят")}>
          Принять возврат
        </Button>,
      );
    }
    items.push(
      <Button size="small" type="link" key="decision" onClick={() => setDecisionOrder(order)}>
        Решение
      </Button>,
      <Button size="small" type="link" key="ledger" onClick={() => setLedgerOrder(order)}>
        Проводки
      </Button>,
    );
    return <Space size={4} wrap>{items}</Space>;
  };

  return (
    <div className="stack">
      <Card size="small">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontWeight: 600 }}>Сквозной заказ</div>
            <div className="muted" style={{ fontSize: 13 }}>
              Создайте заказ и получите решение A / B / C с цифрами по каждому фильтру.
            </div>
          </div>
          <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} onClick={() => setCreateOpen(true)}>
            Создать заказ
          </Button>
        </div>
      </Card>

      <Card size="small" title={`Заказы точки${orders.data ? ` · ${orders.data.length}` : ""}`}>
        <Table
          size="small"
          rowKey="id"
          loading={orders.isLoading}
          dataSource={orders.data ?? []}
          pagination={{ pageSize: 12, hideOnSinglePage: true }}
          scroll={{ x: 1080 }}
          columns={[
            { title: "№", dataIndex: "id", width: 64 },
            {
              title: "SKU",
              key: "sku",
              render: (_: unknown, order: Order) => (
                <div>
                  <div>{order.sku.name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {order.sku.size_class} · {order.sku.seller}
                  </div>
                </div>
              ),
            },
            {
              title: "Маршрут",
              key: "route",
              width: 220,
              render: (_: unknown, order: Order) => (
                <span className="muted" style={{ fontSize: 12 }}>
                  {order.source_pvz.name} → {order.buyer_pvz.name}
                </span>
              ),
            },
            {
              title: "Режим",
              key: "mode",
              width: 90,
              render: (_: unknown, order: Order) => (
                <Space size={6}>
                  <ModeTag mode={order.mode} />
                  <span className="muted" style={{ fontSize: 12 }}>
                    {order.mode === "B" ? `${order.eta_mesh_h ?? "—"} ч` : ""}
                  </span>
                </Space>
              ),
            },
            {
              title: "Статус",
              key: "status",
              width: 170,
              render: (_: unknown, order: Order) => <StatusTag status={order.status} />,
            },
            {
              title: "Mesh",
              dataIndex: "cost_mesh",
              width: 100,
              align: "right",
              render: (value: number) => <span className="num">{fmtRub(value)}</span>,
            },
            {
              title: "Хаб",
              dataIndex: "cost_hub",
              width: 100,
              align: "right",
              render: (value: number) => <span className="num">{fmtRub(value)}</span>,
            },
            { title: "Действия", key: "actions", render: (_: unknown, order: Order) => buttons(order) },
          ]}
        />
      </Card>

      <CreateOrderModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        currentPvzId={pvzId}
        pvzList={pvzList.data ?? []}
      />
      <DecisionDrawer
        order={decisionOrder}
        open={Boolean(decisionOrder)}
        onClose={() => setDecisionOrder(null)}
      />
      <LedgerDrawer order={ledgerOrder} onClose={() => setLedgerOrder(null)} />
    </div>
  );
}

function LedgerDrawer({ order, onClose }: { order: Order | null; onClose: () => void }) {
  const ledger = useLedger(order?.id);
  return (
    <Drawer title={order ? `Проводки по заказу #${order.id}` : "Проводки"} width={560} open={Boolean(order)} onClose={onClose}>
      {ledger.data && (
        <div className="stack">
          <Kpi
            label="Сумма проводок по заказу"
            value={fmtRub(ledger.data.balance)}
            hint="двойная запись: должно быть 0"
            accent={ledger.data.balance === 0 ? "#16A34A" : "#DC2626"}
          />
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={ledger.data.entries}
            columns={[
              { title: "Счёт", dataIndex: "account" },
              { title: "Операция", dataIndex: "type" },
              {
                title: "Сумма",
                dataIndex: "amount",
                align: "right",
                render: (value: number) => (
                  <span className="num" style={{ color: value < 0 ? "#52627A" : "#0F172A" }}>
                    {fmtRub(value)}
                  </span>
                ),
              },
            ]}
          />
        </div>
      )}
    </Drawer>
  );
}

type OrderInput = { sku_id: number; source_pvz_id: number; buyer_pvz_id: number; batch_id?: number };

function CreateOrderModal({
  open,
  onClose,
  currentPvzId,
  pvzList,
}: {
  open: boolean;
  onClose: () => void;
  currentPvzId?: number;
  pvzList: Pvz[];
}) {
  const skus = useSkus();
  const create = useCreateOrder();
  const [form] = Form.useForm<OrderInput>();
  const sourceId = Form.useWatch("source_pvz_id", form);
  const skuId = Form.useWatch("sku_id", form);
  const stock = useStock(open ? sourceId : undefined);
  const [result, setResult] = useState<Order | null>(null);

  const options = useMemo(
    () =>
      (skus.data ?? []).map((sku: Sku) => ({
        value: sku.id,
        label: `${sku.name} · ${sku.size_class} · ${fmtRub(sku.price)}`,
      })),
    [skus.data],
  );

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      source_pvz_id: currentPvzId,
      buyer_pvz_id: pvzList.find((item) => item.id !== currentPvzId)?.id ?? currentPvzId,
      batch_id: undefined,
    });
  }, [open, currentPvzId, pvzList, form]);

  const submit = (values: OrderInput) => {
    create.mutate(
      values,
      {
        onSuccess: (order) => {
          setResult(order);
          message.success(`Заказ #${order.id}: режим ${order.mode}`);
        },
        onError: (error) => message.error(error.message),
      },
    );
  };

  const byName = (part: string) => pvzList.find((item) => item.name.includes(part));

  const runScenario = (scenario: "B" | "A" | "C") => {
    const firstSku = (skus.data ?? []).find((sku) => sku.size_class === "S");
    const mira = byName("Мира");
    const kompros = byName("Компрос");
    const tverskaya = byName("Тверская");
    if (!firstSku || !mira || !kompros || !tverskaya) {
      message.warning("Демо-данные не загружены: выполните make seed");
      return;
    }
    const payload =
      scenario === "B"
        ? { sku_id: firstSku.id, source_pvz_id: mira.id, buyer_pvz_id: kompros.id }
        : scenario === "A"
          ? { sku_id: firstSku.id, source_pvz_id: kompros.id, buyer_pvz_id: kompros.id }
          : { sku_id: firstSku.id, source_pvz_id: mira.id, buyer_pvz_id: tverskaya.id };
    form.setFieldsValue({ ...payload, batch_id: undefined });
    submit(payload);
  };

  return (
    <Modal
      title="Новый заказ и решение решателя"
      open={open}
      forceRender
      onCancel={() => {
        setResult(null);
        onClose();
      }}
      footer={null}
      width={620}
    >
      <div className="stack">
        <Space wrap size={8}>
          <span className="muted" style={{ fontSize: 13 }}>Сценарии демо:</span>
          <Button size="small" disabled={create.isPending} icon={<ThunderboltOutlined aria-hidden="true" />} onClick={() => runScenario("B")}>
            Городской рейс
          </Button>
          <Button size="small" disabled={create.isPending} onClick={() => runScenario("A")}>С полки</Button>
          <Button size="small" disabled={create.isPending} onClick={() => runScenario("C")}>Дальний, через хаб</Button>
        </Space>

        <Form
          form={form}
          layout="vertical"
          onFinish={submit}
        >
          <Form.Item name="sku_id" label="SKU" rules={[{ required: true, message: "Выберите SKU" }]}>
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="Товар продавца"
              options={options}
              onChange={() => form.setFieldValue("batch_id", undefined)}
            />
          </Form.Item>
          <div className="row">
            <Form.Item name="source_pvz_id" label="Откуда (склад)" style={{ flex: 1 }} rules={[{ required: true }]}>
              <Select
                options={pvzList.map((item) => ({ value: item.id, label: item.name }))}
                onChange={() => form.setFieldValue("batch_id", undefined)}
              />
            </Form.Item>
            <Form.Item name="buyer_pvz_id" label="Куда (ПВЗ покупателя)" style={{ flex: 1 }} rules={[{ required: true }]}>
              <Select options={pvzList.map((item) => ({ value: item.id, label: item.name }))} />
            </Form.Item>
          </div>
          <Form.Item name="batch_id" label="Партия">
            <Select
              allowClear
              disabled={!sourceId || !skuId}
              placeholder="По умолчанию — самая ранняя доступная партия"
              options={(stock.data?.batches ?? [])
                .filter((batch) => batch.sku_id === skuId && batch.qty_free > 0)
                .map((batch) => ({ value: batch.id, label: `№${batch.id} · ${batch.qty_free} шт.` }))}
            />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={create.isPending}>
              Создать заказ
            </Button>
            <Button onClick={() => setResult(null)} disabled={!result}>
              Очистить решение
            </Button>
          </Space>
        </Form>

        {result && (
          <div>
            <SectionTitle>Решение по заказу #{result.id}</SectionTitle>
            <DecisionCard decision={result.decision} />
          </div>
        )}

        {!result && (
          <Alert
            type="info"
            showIcon
            icon={<CloseCircleOutlined />}
            message="Подсказка: рейс «Мира → Компрос» уже на 99 заказах, поэтому следующий S-заказ проходит порог."
            description="Если остатка нет в выбранном ПВЗ, API вернёт 409 с причиной — это не ошибка демо, а проверка остатков."
          />
        )}
      </div>
    </Modal>
  );
}

function TripsTab({ pvzId }: { pvzId?: number }) {
  const trips = useTrips();
  const pvzList = usePvzList();
  const action = useTripAction();
  const plan = usePlanTrip();
  const [form] = Form.useForm<{
    from_pvz_id: number;
    to_pvz_id: number;
    kind: "DEDICATED" | "ALONG";
    departs_in_hours: number;
  }>();

  const run = (trip: Trip, act: string, label: string) => {
    action.mutate(
      { tripId: trip.id, action: act },
      {
        onSuccess: () => message.success(`${label}: рейс #${trip.id}`),
        onError: (error) => message.error(error.message),
      },
    );
  };

  return (
    <div className="stack">
      <Card size="small" title="Запланировать рейс">
        <Form
          form={form}
          layout="inline"
          initialValues={{ kind: "DEDICATED", departs_in_hours: 24 }}
          onFinish={(values) => {
            plan.mutate(values, {
              onSuccess: () => message.success("Рейс запланирован"),
              onError: (error) => message.error(error.message),
            });
          }}
          style={{ rowGap: 12 }}
        >
          <Form.Item name="from_pvz_id" label="Откуда" rules={[{ required: true }]}>
            <Select style={{ width: 170 }} options={(pvzList.data ?? []).map((item) => ({ value: item.id, label: item.name }))} />
          </Form.Item>
          <Form.Item name="to_pvz_id" label="Куда" rules={[{ required: true }]}>
            <Select style={{ width: 170 }} options={(pvzList.data ?? []).map((item) => ({ value: item.id, label: item.name }))} />
          </Form.Item>
          <Form.Item name="kind" label="Тип">
            <Select
              style={{ width: 170 }}
              options={[
                { value: "DEDICATED", label: "Выделенный · 4 500 ₽" },
                { value: "ALONG", label: "Попутный · 750 ₽" },
              ]}
            />
          </Form.Item>
          <Form.Item name="departs_in_hours" label="Через, ч">
            <InputNumber min={0} max={240} style={{ width: 100 }} />
          </Form.Item>
          <Button type="primary" htmlType="submit">Запланировать</Button>
        </Form>
      </Card>

      <Card size="small" title="Рейсы">
        <Table
          size="small"
          rowKey="id"
          loading={trips.isLoading}
          dataSource={trips.data ?? []}
          pagination={false}
          scroll={{ x: 900 }}
          columns={[
            { title: "№", dataIndex: "id", width: 60 },
            {
              title: "Маршрут",
              key: "route",
              render: (_: unknown, trip: Trip) => (
                <div>
                  <div>
                    {trip.from_pvz.name} → {trip.to_pvz.name}
                    {trip.from_pvz.id === pvzId || trip.to_pvz.id === pvzId ? (
                      <Tag color="blue" style={{ marginLeft: 8 }}>ваш ПВЗ</Tag>
                    ) : null}
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {trip.kind === "DEDICATED" ? "выделенный" : "попутный"} · {fmtRub(trip.cost)}
                  </div>
                </div>
              ),
            },
            {
              title: "Заказов",
              key: "orders",
              width: 130,
              render: (_: unknown, trip: Trip) => (
                <span className="num">
                  {trip.orders} · {trip.used_um}/{trip.capacity_um} УМ
                </span>
              ),
            },
            {
              title: "Отправление",
              dataIndex: "departs_at",
              width: 160,
              render: (value: string) => value.replace("T", " ").slice(0, 16),
            },
            {
              title: "Статус",
              key: "status",
              width: 150,
              render: (_: unknown, trip: Trip) => <StatusTag status={trip.status} />,
            },
            {
              title: "Действия",
              key: "actions",
              render: (_: unknown, trip: Trip) => (
                <Space size={4} wrap>
                  {trip.status === "PLANNED" && (
                    <Button size="small" type="primary" onClick={() => run(trip, "depart", "Рейс отправлен")}>
                      Отправить
                    </Button>
                  )}
                  {trip.status === "IN_TRANSIT" && (
                    <Button size="small" type="primary" onClick={() => run(trip, "arrive", "Рейс прибыл")}>
                      Прибыл
                    </Button>
                  )}
                  {["PLANNED", "IN_TRANSIT"].includes(trip.status) && (
                    <Tooltip title="Заказы пересчитаются: другой рейс или хаб">
                      <Button size="small" danger onClick={() => run(trip, "fail", "Сбой обработан")}>
                        Сбой
                      </Button>
                    </Tooltip>
                  )}
                </Space>
              ),
            },
          ]}
        />
        <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
          «Отправить» автоматически собирает зарезервированные заказы и пишет проводки за сборку.
          «Сбой» пересчитывает каждый заказ: если следующий рейс проходит фильтры, остаётся B, иначе C.
        </div>
      </Card>
    </div>
  );
}

function AnalyticsTab({ pvzId }: { pvzId?: number }) {
  const analytics = usePvzAnalytics(pvzId);
  const data = analytics.data;

  return (
    <div className="stack">
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card size="small"><Kpi label="Выручка ПВЗ" value={data ? fmtRub(data.revenue) : "—"} hint="приёмка, хранение, сборка, бонусы" /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small"><Kpi label="Труд" value={data ? fmtRub(data.labor) : "—"} hint="400 ₽/ч по нормативу операций" /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small"><Kpi label="Расходники и место" value={data ? fmtRub(data.overhead) : "—"} hint="допущение по классу" /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Kpi
              label="Вклад"
              value={data ? fmtRub(data.contribution) : "—"}
              hint={data ? `${fmtRub(data.contribution_per_um_day)} на УМ-день` : undefined}
              accent={data && data.contribution >= 0 ? "#16A34A" : "#DC2626"}
            />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="Выручка по дням">
        <div style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data?.days ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} width={70} />
              <ChartTooltip formatter={(value) => fmtRub(typeof value === "number" ? value : undefined)} />
              <Bar dataKey="revenue" name="Выручка" fill="#2563EB" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card size="small" title="Последние проводки">
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={data?.ledger ?? []}
          scroll={{ x: 640 }}
          columns={[
            { title: "Когда", dataIndex: "created_at", width: 160, render: (v: string) => v.replace("T", " ").slice(0, 16) },
            { title: "Операция", dataIndex: "type" },
            { title: "Заказ", dataIndex: "order_id", width: 80, render: (v: number | null) => v ?? "—" },
            { title: "Сумма", dataIndex: "amount", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
          ]}
        />
      </Card>
    </div>
  );
}
