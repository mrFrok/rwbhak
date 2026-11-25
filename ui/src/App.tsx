import {
  ClockCircleOutlined,
  LineChartOutlined,
  ShopOutlined,
  ShoppingOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Tooltip, message } from "antd";
import dayjs from "dayjs";
import { useMemo } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAdvanceTime, useTime } from "./api/hooks";
import ModelPage from "./pages/ModelPage";
import PvzPage from "./pages/PvzPage";
import SellerPage from "./pages/SellerPage";

const { Sider, Header, Content } = Layout;

const MENU = [
  { key: "/pvz", icon: <ShopOutlined />, label: "ПВЗ" },
  { key: "/seller", icon: <ShoppingOutlined />, label: "Продавец" },
  { key: "/model", icon: <LineChartOutlined />, label: "Модель" },
];

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const time = useTime();
  const advance = useAdvanceTime();

  const selected = useMemo(
    () => MENU.find((item) => location.pathname.startsWith(item.key))?.key ?? "/pvz",
    [location.pathname],
  );

  const current = MENU.find((item) => item.key === selected);

  const onAdvance = () => {
    advance.mutate(1, {
      onSuccess: () => message.success("Модельные часы сдвинуты на сутки"),
      onError: (error) => message.error(error.message),
    });
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={236} breakpoint="lg" collapsedWidth={0} trigger={null}>
        <div className="sider-brand">
          <span className="sider-brand__mark">RM</span>
          <div>
            <div className="sider-brand__name">RWB Mesh</div>
            <div className="sider-brand__sub">доставка с полки ПВЗ</div>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          items={MENU}
          onClick={({ key }) => navigate(key)}
          style={{ borderInlineEnd: "none" }}
        />
        <div className="sider-clock">
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <ClockCircleOutlined />
            <span>Модельное время</span>
          </div>
          <div className="num" style={{ fontSize: 15, color: "#fff", margin: "6px 0 10px" }}>
            {time.data ? dayjs(time.data.now).format("DD.MM.YYYY HH:mm") : "—"}
          </div>
          <Tooltip title="Сдвинуть модельные часы на сутки: хранение, алерты и рейсы считаются от них">
            <Button
              size="small"
              block
              loading={advance.isPending}
              onClick={onAdvance}
              style={{ background: "#334155", borderColor: "#475569", color: "#fff" }}
            >
              +1 день
            </Button>
          </Tooltip>
        </div>
      </Sider>
      <Layout>
        <Header className="topbar" style={{ lineHeight: 1.4 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 15 }}>{current?.label}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              Демо на синтетических данных · все суммы — допущения команды
            </div>
          </div>
          <a href="/docs" target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
            Swagger API
          </a>
        </Header>
        <nav className="mobile-nav" aria-label="Разделы приложения">
          {MENU.map(({ key, label }) => (
            <Button key={key} type={key === selected ? "primary" : "text"} onClick={() => navigate(key)}>
              {label}
            </Button>
          ))}
          <Button loading={advance.isPending} onClick={onAdvance}>+1 день</Button>
        </nav>
        <Content className="content">
          <Routes>
            <Route path="/" element={<Navigate to="/pvz" replace />} />
            <Route path="/pvz" element={<PvzPage />} />
            <Route path="/seller" element={<SellerPage />} />
            <Route path="/model" element={<ModelPage />} />
            <Route path="*" element={<Navigate to="/pvz" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
