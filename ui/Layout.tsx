import { useState } from 'react';
import { Alert, App as AntApp, Button, Flex, Layout, Menu, Select, Switch, Typography } from 'antd';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useGet } from '../api/hooks';
import type { Pvz } from '../api/types';
import { errorMessage } from '../api/client';
import { formatNum } from '../lib/format';
import { useSettings } from '../state/settings';

const { Sider, Content } = Layout;

function SidePanel() {
  const { mock, setMock, pvzId, setPvzId, sellerId, setSellerId, clock, advance } = useSettings();
  const { message } = AntApp.useApp();
  const pvz = useGet<Pvz[]>('/pvz');
  const [busy, setBusy] = useState(false);
  const loc = useLocation();
  const selected = loc.pathname.startsWith('/pvz') ? 'pvz' : loc.pathname.startsWith('/seller') ? 'seller' : 'model';

  const step = async (h: number) => {
    setBusy(true);
    try { await advance(h); } catch (e) { message.error(errorMessage(e)); } finally { setBusy(false); }
  };

  const pvzOptions = (pvz.data ?? []).map((p) => ({ value: p.id, label: p.name }));
  const effectivePvz = pvzId != null && pvzOptions.some((o) => o.value === pvzId) ? pvzId : pvzOptions[0]?.value ?? null;

  return (
    <Flex vertical gap={20} style={{ padding: 16 }}>
      <Typography.Title level={5} style={{ margin: 0 }}>Mesh-доставка</Typography.Title>
      <Menu
        mode="inline" selectedKeys={[selected]} style={{ border: 0, background: 'transparent' }}
        items={[
          { key: 'model', label: <Link to="/model">Модель</Link> },
          { key: 'pvz', label: <Link to="/pvz">ПВЗ</Link> },
          { key: 'seller', label: <Link to="/seller">Продавец</Link> },
        ]}
      />

      <Flex vertical gap={6}>
        <Typography.Text strong>Данные</Typography.Text>
        <Flex gap={8} align="center">
          <Switch checked={mock} onChange={setMock} size="small" aria-label="Заглушки" />
          <span>Заглушки (без backend)</span>
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>{mock ? 'Источник: JSON из src/mock' : 'Источник: /api'}</Typography.Text>
        {pvz.error && <Alert type="error" showIcon message={errorMessage(pvz.error)} />}
      </Flex>

      <Flex vertical gap={6}>
        <Typography.Text strong>ПВЗ</Typography.Text>
        <Select value={effectivePvz} onChange={setPvzId} options={pvzOptions} loading={pvz.isLoading} placeholder="Нет данных" />
        <Typography.Text strong style={{ marginTop: 8 }}>Продавец</Typography.Text>
        {/* В контракте нет списка продавцов: пока 1–10, как в синтетике. */}
        <Select value={sellerId} onChange={setSellerId} options={Array.from({ length: 10 }, (_, i) => ({ value: i + 1, label: `Продавец ${i + 1}` }))} />
      </Flex>

      <Flex vertical gap={6}>
        <Typography.Text strong>Модельное время</Typography.Text>
        <Flex gap={8}>
          <Button block disabled={busy} onClick={() => step(1)}>+1 час</Button>
          <Button block disabled={busy} onClick={() => step(24)}>+1 день</Button>
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {clock ? `Сейчас: ${clock.now_iso.replace('T', ' ')} (прошло ${formatNum(clock.now_h)} ч)` : 'Время неизвестно: нажмите «+1 час» или проверьте API.'}
        </Typography.Text>
      </Flex>
    </Flex>
  );
}

export function AppLayout() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={260} breakpoint="lg" collapsedWidth={0} theme="light" style={{ borderInlineEnd: '1px solid rgba(128,128,128,.2)' }}>
        <SidePanel />
      </Sider>
      <Content style={{ padding: '24px clamp(16px, 3vw, 40px)', maxWidth: 1280 }}>
        <Outlet />
      </Content>
    </Layout>
  );
}
