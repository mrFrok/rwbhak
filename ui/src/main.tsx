import { ConfigProvider, App as AntApp, theme as antdTheme } from "antd";
import ruRU from "antd/locale/ru_RU";
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: 0 },
  },
});

const palette = {
  primary: "#2563EB",
  success: "#16A34A",
  warning: "#D97706",
  error: "#DC2626",
  info: "#0EA5E9",
  bg: "#F4F6F9",
  surface: "#FFFFFF",
  ink: "#0F172A",
  muted: "#52627A",
  border: "#E2E8F0",
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={ruRU}
      theme={{
        algorithm: antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: palette.primary,
          colorSuccess: palette.success,
          colorWarning: palette.warning,
          colorError: palette.error,
          colorInfo: palette.info,
          colorBgLayout: palette.bg,
          colorBgContainer: palette.surface,
          colorText: palette.ink,
          colorTextSecondary: palette.muted,
          colorBorder: palette.border,
          colorBorderSecondary: palette.border,
          borderRadius: 10,
          fontFamily:
            "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
          fontSize: 14,
          controlHeight: 36,
        },
        components: {
          Layout: { siderBg: palette.ink, headerBg: palette.surface, bodyBg: palette.bg },
          Menu: {
            darkItemBg: palette.ink,
            darkSubMenuItemBg: palette.ink,
            darkItemSelectedBg: "#1E293B",
            darkItemSelectedColor: "#FFFFFF",
            darkItemColor: "#94A3B8",
            itemBorderRadius: 8,
          },
          Table: {
            headerBg: "#F8FAFC",
            headerColor: palette.muted,
            headerSplitColor: "transparent",
            rowHoverBg: "#F1F5F9",
            cellPaddingBlock: 10,
          },
          Card: { paddingLG: 20 },
          Tabs: { itemSelectedColor: palette.primary, inkBarColor: palette.primary },
        },
      }}
    >
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
