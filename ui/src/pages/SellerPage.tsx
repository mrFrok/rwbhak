import { Alert, Card, Col, Row, Select, Table, Tabs, Tag } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRecommendPvz, useSellerAnalytics, useSellers, useSkus } from "../api/hooks";
import type { SellerAnalytics } from "../api/types";
import { Kpi, ModeTag, StatusTag, fmtRub } from "../components/ui";

export default function SellerPage() {
  const sellers = useSellers();
  const [sellerId, setSellerId] = useState<number>();

  useEffect(() => {
    if (sellerId === undefined && sellers.data?.length) setSellerId(sellers.data[0].id);
  }, [sellers.data, sellerId]);

  const analytics = useSellerAnalytics(sellerId);

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Продавец</h1>
          <p>
            Полный разбор прибыли по каждому заказу: комиссия, эквайринг, логистика,
            хранение, возвраты и налог. Тарифы — из бизнес-модели v0.3.
          </p>
        </div>
        <Select
          style={{ width: 260 }}
          value={sellerId}
          onChange={setSellerId}
          options={(sellers.data ?? []).map((item) => ({
            value: item.id,
            label: item.city ? `${item.name} · ${item.city}` : item.name,
          }))}
        />
      </div>

      <SellerBody sellerId={sellerId} analytics={analytics.data} loading={analytics.isLoading} />
    </div>
  );
}

function SellerBody({ sellerId, analytics, loading }: { sellerId?: number; analytics?: SellerAnalytics; loading: boolean }) {
  const params = useParams();
  const skus = useSkus();
  const sellerSkus = useMemo(
    () => (skus.data ?? []).filter((sku) => sku.seller_id === sellerId),
    [skus.data, sellerId],
  );
  const [recommendSku, setRecommendSku] = useState<number | undefined>();
  useEffect(() => {
    if (recommendSku === undefined && sellerSkus.length) setRecommendSku(sellerSkus[0].id);
  }, [sellerSkus, recommendSku]);
  const recommendation = useRecommendPvz(sellerId, recommendSku);
  const storageRows = useMemo(
    () => [
      { key: "1-3", days: "Дни 1–3", seller: "0 ₽", pvz: "3 ₽ × УМ-день", note: "включено" },
      { key: "4-7", days: "Дни 4–7", seller: "3 ₽ × УМ-день", pvz: "3 ₽ × УМ-день", note: "тариф растёт" },
      { key: "8-14", days: "Дни 8–14", seller: "6 ₽ × УМ-день", pvz: "3 ₽ × УМ-день", note: "предложение забрать" },
      { key: "15+", days: "Дни 15+", seller: "10 ₽ × УМ-день", pvz: "3 ₽ × УМ-день", note: "вывоз ближайшим рейсом" },
    ],
    [],
  );

  if (!analytics) {
    return <Card loading={loading} />;
  }

  const { totals } = analytics;

  return (
    <div className="stack">
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card size="small"><Kpi label="Цена заказов" value={fmtRub(totals.price)} hint="сумма по заказам" /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small"><Kpi label="Комиссия и налог" value={fmtRub(totals.commission)} hint="15% + УСН 6% с выручки" /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small"><Kpi label="Хранение" value={fmtRub(totals.storage)} hint="платные дни с 4-го" /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Kpi
              label="Чистая маржа"
              value={fmtRub(totals.margin)}
              hint={`маржинальность ${totals.margin_pct.toFixed(1)}%`}
              accent={totals.margin >= 0 ? "#16A34A" : "#DC2626"}
            />
          </Card>
        </Col>
      </Row>

      <Alert type="info" showIcon message={analytics.note} />

      <Tabs
        defaultActiveKey="orders"
        items={[
          {
            key: "orders",
            label: "Заказы",
            children: (
              <Card size="small" title={analytics.seller.name}>
                <Table
                  size="small"
                  rowKey="order_id"
                  dataSource={analytics.orders}
                  pagination={{ pageSize: 12, hideOnSinglePage: true }}
                  scroll={{ x: 1280 }}
                  columns={[
                    { title: "№", dataIndex: "order_id", width: 70 },
                    { title: "SKU", dataIndex: "sku" },
                    { title: "Класс", dataIndex: "size_class", width: 80 },
                    {
                      title: "Режим",
                      dataIndex: "mode",
                      width: 80,
                      render: (mode: "A" | "B" | "C") => <ModeTag mode={mode} />,
                    },
                    {
                      title: "Статус",
                      dataIndex: "status",
                      width: 150,
                      render: (status: string) => <StatusTag status={status} />,
                    },
                    { title: "Дней", dataIndex: "storage_days", width: 70, align: "right" },
                    { title: "Цена", dataIndex: "price", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                    { title: "Товар", dataIndex: "unit_cost", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                    { title: "Комиссия", dataIndex: "commission", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                    { title: "Эквайринг", dataIndex: "acquiring", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                    { title: "Логистика", dataIndex: "logistics", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                    { title: "Хранение", dataIndex: "storage", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                    { title: "Возвраты", dataIndex: "returns", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                    { title: "Налог", dataIndex: "tax", align: "right", render: (v: number) => <span className="num">{fmtRub(v)}</span> },
                    {
                      title: "Маржа",
                      dataIndex: "margin",
                      align: "right",
                      render: (v: number, row) => (
                        <span className="num" style={{ color: v >= 0 ? "#16A34A" : "#DC2626", fontWeight: 600 }}>
                          {fmtRub(v)}
                          <span className="muted" style={{ fontWeight: 400 }}> · {row.margin_pct.toFixed(1)}%</span>
                        </span>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "recommend",
            label: "Куда везти",
            children: (
              <Card size="small">
                <div className="row" style={{ alignItems: "center", marginBottom: 12 }}>
                  <Select
                    style={{ width: 320 }}
                    value={recommendSku}
                    onChange={setRecommendSku}
                    placeholder="Выберите SKU"
                    options={sellerSkus.map((sku) => ({
                      value: sku.id,
                      label: `${sku.name} · ${sku.size_class}`,
                    }))}
                  />
                  <span className="muted" style={{ fontSize: 13 }}>
                    {recommendation.data?.note ?? "Балл = спрос × 10 + место × 0.5 − остаток × 4"}
                  </span>
                </div>
                <Table
                  size="small"
                  rowKey="pvz_id"
                  loading={recommendation.isLoading}
                  dataSource={recommendation.data?.items ?? []}
                  pagination={false}
                  columns={[
                    { title: "ПВЗ", dataIndex: "pvz_name" },
                    { title: "Город", dataIndex: "city" },
                    { title: "Спрос за 30 дн", dataIndex: "demand", align: "right" },
                    { title: "Остаток", dataIndex: "stock", align: "right" },
                    { title: "Свободно, УМ", dataIndex: "free_um", align: "right" },
                    {
                      title: "Балл",
                      dataIndex: "score",
                      align: "right",
                      render: (value: number, row) => (
                        <span style={{ fontWeight: 600 }}>
                          {value.toFixed(1)}
                          {row.hint ? <Tag color="green" style={{ marginLeft: 8 }}>{row.hint}</Tag> : null}
                        </span>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "tariffs",
            label: "Тарифы хранения",
            children: (
              <div className="stack">
                <Card size="small" title="Прогрессивный тариф: продавец платит, ПВЗ получает с первого дня">
                  <Table
                    size="small"
                    rowKey="key"
                    pagination={false}
                    dataSource={storageRows}
                    columns={[
                      { title: "Период", dataIndex: "days" },
                      { title: "Продавец", dataIndex: "seller" },
                      { title: "ПВЗ", dataIndex: "pvz" },
                      { title: "Правило", dataIndex: "note" },
                    ]}
                  />
                  <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
                    За 14 дней единица S: продавец платит 54 ₽, ПВЗ получает 42 ₽. На 7-й день —
                    алерт «нет продаж», на 15-й — вывоз (10 ₽/УМ-день + 35 ₽ за единицу) и
                    блокировка пополнения. Обратная логистика при отказе — 50 ₽ за единицу.
                  </div>
                </Card>

                <Card size="small" title="Реестр допущений">
                  <Table
                    size="small"
                    rowKey="code"
                    pagination={false}
                    dataSource={params.data?.assumptions ?? []}
                    columns={[
                      { title: "Код", dataIndex: "code", width: 180, render: (v: string) => <code>{v}</code> },
                      { title: "Допущение", dataIndex: "name" },
                      { title: "Значение", key: "value", width: 160, render: (_: unknown, row) => `${row.value} ${row.unit}` },
                    ]}
                  />
                  <Tag color="blue" style={{ marginTop: 12 }}>Не тарифы RWB</Tag>
                </Card>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
