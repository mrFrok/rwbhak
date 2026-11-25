import {
  ArrowRightOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
} from "@ant-design/icons";
import { Card, Drawer, Tag, Tooltip } from "antd";
import type { ReactNode } from "react";
import type { Decision, Mode, Order } from "../api/types";

export const MODE_META: Record<Mode, { label: string; short: string; color: string }> = {
  A: { label: "С полки ПВЗ", short: "A", color: "#15803D" },
  B: { label: "Рейс ПВЗ → ПВЗ", short: "B", color: "#C2410C" },
  C: { label: "Через хаб", short: "C", color: "#475569" },
};

export const STATUS_META: Record<string, { label: string; color: string }> = {
  CREATED: { label: "Создан", color: "#64748B" },
  RESERVED: { label: "Зарезервирован", color: "#2563EB" },
  PICKED: { label: "Собран", color: "#0EA5E9" },
  IN_TRIP: { label: "В рейсе", color: "#EA580C" },
  ARRIVED: { label: "Прибыл в ПВЗ", color: "#16A34A" },
  ISSUED: { label: "Выдан", color: "#16A34A" },
  ROUTED_HUB: { label: "Через хаб", color: "#64748B" },
  RETURN_REQUESTED: { label: "Возврат запрошен", color: "#D97706" },
  RETURN_IN_TRANSIT: { label: "Возврат в пути", color: "#D97706" },
  RETURNED: { label: "Возвращён", color: "#64748B" },
  PLANNED: { label: "Запланирован", color: "#2563EB" },
  IN_TRANSIT: { label: "В пути", color: "#0EA5E9" },
  FAILED: { label: "Сорван", color: "#DC2626" },
};

const rubFormatter = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export function fmtRub(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${rubFormatter.format(value)} ₽`;
}

export function fmtNum(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return rubFormatter.format(value);
}

export function Kpi({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="kpi">
      <span className="kpi__label">{label}</span>
      <span className="kpi__value" style={accent ? { color: accent } : undefined}>
        {value}
      </span>
      {hint ? <span className="kpi__hint">{hint}</span> : null}
    </div>
  );
}

export function ModeTag({ mode }: { mode: Mode }) {
  const meta = MODE_META[mode];
  return (
    <Tooltip title={meta.label}>
      <Tag color={meta.color} style={{ marginInlineEnd: 0, fontWeight: 600 }}>
        {meta.short}
      </Tag>
    </Tooltip>
  );
}

export function StatusTag({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? { label: status, color: "#64748B" };
  return (
    <span style={{ whiteSpace: "nowrap" }}>
      <span className="mode-dot" style={{ background: meta.color }} />
      {meta.label}
    </span>
  );
}

export function DecisionCard({ decision, dense }: { decision: Decision; dense?: boolean }) {
  const filters = decision.filters ?? [];
  const meta = MODE_META[decision.mode];
  return (
    <Card size="small" style={{ borderColor: meta.color }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
            borderRadius: 8,
            background: meta.color,
            color: "#fff",
            fontWeight: 700,
          }}
        >
          {decision.mode}
        </span>
        <div>
          <div style={{ fontWeight: 600 }}>{meta.label}</div>
          <div className="muted" style={{ fontSize: 13 }}>
            {decision.reason}
          </div>
        </div>
      </div>

      <div className="row" style={{ gap: 24, marginBottom: filters.length ? 12 : 0 }}>
        <div>
          <div className="kpi__label">Mesh</div>
          <div className="num" style={{ fontWeight: 600 }}>{fmtRub(decision.cost_mesh)}</div>
        </div>
        <div>
          <div className="kpi__label">Через хаб</div>
          <div className="num" style={{ fontWeight: 600 }}>{fmtRub(decision.cost_hub)}</div>
        </div>
        <div>
          <div className="kpi__label">Экономия</div>
          <div className="num" style={{ fontWeight: 600, color: decision.saving > 0 ? "#16A34A" : "#64748B" }}>
            {fmtRub(decision.saving)}
          </div>
        </div>
        <div>
          <div className="kpi__label">Срок</div>
          <div className="num" style={{ fontWeight: 600 }}>
            {decision.eta_mesh_h != null ? `${decision.eta_mesh_h.toFixed(0)} ч` : "—"}
            <span className="muted"> / {decision.eta_hub_h} ч</span>
          </div>
        </div>
      </div>

      {filters.length > 0 && (
        <div>
          {filters.map((filter) => (
            <div className="decision-filter" key={filter.code}>
              {filter.ok ? (
                <CheckCircleFilled style={{ color: "#16A34A" }} aria-label="пройден" />
              ) : (
                <CloseCircleFilled style={{ color: "#DC2626" }} aria-label="не пройден" />
              )}
              <div>
                <div style={{ fontWeight: 500 }}>{filter.title}</div>
                {!dense && (
                  <div className="decision-filter__actual">
                    {filter.actual} · нужно {filter.limit}
                  </div>
                )}
              </div>
              <span className="muted" style={{ fontSize: 12 }}>
                {filter.ok ? "ок" : "нет"}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function DecisionDrawer({
  order,
  open,
  onClose,
}: {
  order: Order | null;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Drawer
      title={order ? `Заказ #${order.id}` : "Заказ"}
      width={520}
      open={open}
      onClose={onClose}
    >
      {order && (
        <div className="stack">
          <div className="muted">
            {order.sku.name} · {order.sku.size_class} · {fmtRub(order.sku.price)}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Tag>{order.source_pvz.name}</Tag>
            <ArrowRightOutlined />
            <Tag>{order.buyer_pvz.name}</Tag>
          </div>
          <DecisionCard decision={order.decision} />
          <div className="muted" style={{ fontSize: 12 }}>
            Снимок решения сохранён в заказе: интерфейс показывает, почему режим был выбран
            в момент создания, даже если партия уже изменилась.
          </div>
        </div>
      )}
    </Drawer>
  );
}

export function SectionTitle({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <h2 className="panel-title">{children}</h2>
      {hint ? <div className="muted" style={{ fontSize: 13 }}>{hint}</div> : null}
    </div>
  );
}
