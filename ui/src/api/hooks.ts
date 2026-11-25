import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "./client";
import type {
  AlertRow,
  Compare,
  Ledger,
  Order,
  Params,
  Pvz,
  PvzAnalytics,
  Seller,
  SellerAnalytics,
  Sku,
  Stock,
  Threshold,
  TimeInfo,
  Trip,
} from "./types";

function useInvalidateAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

export const usePvzList = () =>
  useQuery({ queryKey: ["pvz"], queryFn: () => get<Pvz[]>("/pvz") });

export const useSellers = () =>
  useQuery({ queryKey: ["sellers"], queryFn: () => get<Seller[]>("/sellers") });

export const useSkus = () =>
  useQuery({ queryKey: ["skus"], queryFn: () => get<Sku[]>("/skus") });

export const useStock = (pvzId?: number) =>
  useQuery({
    queryKey: ["stock", pvzId],
    queryFn: () => get<Stock>(`/pvz/${pvzId}/stock`),
    enabled: Boolean(pvzId),
  });

export const useAlerts = (pvzId?: number) =>
  useQuery({
    queryKey: ["alerts", pvzId],
    queryFn: () => get<AlertRow[]>(`/pvz/${pvzId}/alerts`),
    enabled: Boolean(pvzId),
  });

export const useOrders = (pvzId?: number, sellerId?: number) =>
  useQuery({
    queryKey: ["orders", pvzId ?? null, sellerId ?? null],
    queryFn: () => {
      const query = new URLSearchParams();
      if (pvzId) query.set("pvz_id", String(pvzId));
      if (sellerId) query.set("seller_id", String(sellerId));
      return get<Order[]>(`/orders?${query.toString()}`);
    },
    enabled: Boolean(pvzId || sellerId),
  });

export const useTrips = () =>
  useQuery({ queryKey: ["trips"], queryFn: () => get<Trip[]>("/trips") });

export const usePvzAnalytics = (pvzId?: number) =>
  useQuery({
    queryKey: ["analytics-pvz", pvzId],
    queryFn: () => get<PvzAnalytics>(`/analytics/pvz/${pvzId}`),
    enabled: Boolean(pvzId),
  });

export const useSellerAnalytics = (sellerId?: number) =>
  useQuery({
    queryKey: ["analytics-seller", sellerId],
    queryFn: () => get<SellerAnalytics>(`/analytics/seller/${sellerId}`),
    enabled: Boolean(sellerId),
  });

export const useParams = () =>
  useQuery({ queryKey: ["params"], queryFn: () => get<Params>("/params") });

export const useTime = () =>
  useQuery({ queryKey: ["time"], queryFn: () => get<TimeInfo>("/time") });

export const useCompare = (kind: "DEDICATED" | "ALONG" = "DEDICATED") =>
  useQuery({
    queryKey: ["compare", kind],
    queryFn: () => get<Compare>(`/compare?kind=${kind}`),
  });

export const useThreshold = () =>
  useQuery({ queryKey: ["threshold"], queryFn: () => get<Threshold>("/threshold") });

export const useLedger = (orderId?: number) =>
  useQuery({
    queryKey: ["ledger", orderId],
    queryFn: () => get<Ledger>(`/orders/${orderId}/ledger`),
    enabled: Boolean(orderId),
  });

export function useCreateOrder() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: {
      sku_id: number;
      buyer_pvz_id: number;
      source_pvz_id?: number;
      batch_id?: number;
    }) => post<Order>("/orders", body),
    onSuccess: invalidate,
  });
}

export function useReceiveBatch() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: {
      sku_id: number;
      pvz_id: number;
      qty: number;
      declared_class: string;
      actual_class?: string;
    }) => post<Record<string, unknown>>("/batches", body),
    onSuccess: invalidate,
  });
}

export function useOrderAction() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ orderId, action }: { orderId: number; action: string }) =>
      post<Order>(`/orders/${orderId}/${action}`),
    onSuccess: invalidate,
  });
}

export function useTripAction() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ tripId, action }: { tripId: number; action: string }) =>
      post<Trip>(`/trips/${tripId}/${action}`),
    onSuccess: invalidate,
  });
}

export function usePlanTrip() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: {
      from_pvz_id: number;
      to_pvz_id: number;
      kind: "DEDICATED" | "ALONG";
      departs_in_hours: number;
    }) => post<Trip>("/trips/plan", body),
    onSuccess: invalidate,
  });
}

export function useAdvanceTime() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (days: number) => post<{ now: string }>("/time/advance", { days }),
    onSuccess: invalidate,
  });
}

export function useSimulate() {
  return useMutation({
    mutationFn: (body: { orders: number; seed: number; kind: "DEDICATED" | "ALONG"; days: number }) =>
      post<Compare>("/simulate", body),
  });
}
