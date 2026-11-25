export type Mode = "A" | "B" | "C";

export interface FilterResult {
  code: string;
  title: string;
  ok: boolean;
  actual: string;
  limit: string;
}

export interface Decision {
  mode: Mode;
  eta_mesh_h: number | null;
  eta_hub_h: number;
  cost_mesh: number;
  cost_hub: number;
  saving: number;
  trip_orders: number;
  filters?: FilterResult[];
  reason: string;
  blocked_by?: string[];
}

export interface Pvz {
  id: number;
  name: string;
  address: string;
  city: string;
  city_id: number;
  capacity_um: number;
  available_um: number;
  reserve_pct: number;
  quiet_windows: string;
}

export interface Seller {
  id: number;
  name: string;
  contact: string;
}

export interface Sku {
  id: number;
  name: string;
  seller_id: number;
  seller: string;
  size_class: string;
  um: number;
  price: number;
  unit_cost: number;
  special: boolean;
}

export interface BatchRow {
  id: number;
  sku_id: number;
  sku: string;
  size_class: string;
  um: number;
  qty: number;
  qty_free: number;
  received_at: string;
  declared_class: string;
  actual_class: string;
}

export interface Stock {
  pvz: {
    id: number;
    name: string;
    address: string;
    city: string;
    capacity_um: number;
    available_um: number;
    quiet_windows: string;
  };
  units: number;
  free_um: number;
  used_um: number;
  load_pct: number;
  space_free_um: number;
  batches: BatchRow[];
}

export interface AlertRow {
  batch_id: number;
  type: string;
  sku: string;
  age_days: number;
  note: string;
}

export interface Order {
  id: number;
  status: string;
  mode: Mode;
  sku: {
    id: number;
    name: string;
    size_class: string;
    price: number;
    seller_id: number;
    seller: string;
  };
  source_pvz: { id: number; name: string };
  buyer_pvz: { id: number; name: string };
  trip_id: number | null;
  eta_mesh_h: number | null;
  eta_hub_h: number;
  cost_mesh: number;
  cost_hub: number;
  saving: number;
  decision: Decision;
  created_at: string;
  picked_at: string | null;
  issued_at: string | null;
}

export interface Trip {
  id: number;
  status: string;
  kind: "DEDICATED" | "ALONG";
  from_pvz: { id: number; name: string };
  to_pvz: { id: number; name: string };
  departs_at: string;
  cost: number;
  capacity_um: number;
  used_um: number;
  free_um: number;
  orders: number;
  order_list?: Order[];
  rerouted?: { to_other_trip: number; to_hub: number };
}

export interface LedgerEntry {
  id: number;
  account: string;
  type: string;
  amount: number;
  line_no: number;
  created_at: string;
}

export interface Ledger {
  order_id: number;
  balance: number;
  entries: LedgerEntry[];
}

export interface PvzAnalytics {
  pvz: { id: number; name: string; city: string };
  revenue: number;
  revenue_by_type: Record<string, number>;
  labor: number;
  overhead: number;
  contribution: number;
  units: number;
  contribution_per_um_day: number;
  days: { date: string; revenue: number }[];
  ledger: LedgerEntry[];
  stock: Stock;
  note: string;
}

export interface SellerAnalytics {
  seller: { id: number; name: string };
  totals: {
    price: number;
    margin: number;
    margin_pct: number;
    commission: number;
    storage: number;
    returns: number;
  };
  orders: {
    order_id: number;
    sku: string;
    size_class: string;
    status: string;
    mode: Mode;
    created_at: string;
    storage_days: number;
    price: number;
    unit_cost: number;
    commission: number;
    acquiring: number;
    logistics: number;
    storage: number;
    returns: number;
    tax: number;
    margin: number;
    margin_pct: number;
  }[];
  note: string;
}

export interface Compare {
  flow_orders: number;
  orders_per_day: number;
  trip_kind: string;
  trip_cost: number;
  totals: {
    hub_cost: number;
    mesh_cost: number;
    saving: number;
    saving_pct: number;
    cost_per_order_hub: number;
    cost_per_order_mesh: number;
  };
  mesh: { orders: number; share_pct: number; trips: number };
  hub: { orders: number; share_pct: number };
  rejected_trips: number;
  thresholds: Record<string, number>;
  pilot: {
    fixed_cost_month: number;
    trips_per_month: number;
    avg_saving: number;
    breakeven_dedicated: number;
    breakeven_along: number;
    rows: { orders: number; effect_dedicated: number; effect_along: number }[];
  };
  sensitivity?: {
    parameter: string;
    delta_pct: number;
    cost_per_order: number;
    saving_vs_base_pct: number;
  }[];
  params?: { orders: number; seed: number; kind: string; days: number };
}

export interface Threshold {
  class: string;
  trip_kind: string;
  trip_cost: number;
  threshold: number;
  points: { orders: number; mesh: number; hub: number; load_um: number }[];
}

export interface Assumption {
  code: string;
  name: string;
  value: number | string;
  unit: string;
  source: string;
}

export interface Params {
  assumptions: Assumption[];
  mix: Record<string, number>;
  note: string;
}

export interface TimeInfo {
  now: string;
}
