import { Card, Col, Flex, Row, Statistic, Table, Typography } from 'antd';
import type { Order } from '../api/types';
import { formatHours, formatRub } from '../lib/format';
import { MODE_TEXT, ModeBadge } from './ModeBadge';

const STATUS_TEXT: Record<string, string> = {
  RESERVED: 'зарезервирован', PICKED: 'собран', IN_TRIP: 'в рейсе', ARRIVED: 'прибыл', ISSUED: 'выдан',
  RETURN_REQUESTED: 'возврат запрошен', RETURN_IN_TRANSIT: 'возврат в пути', RETURNED: 'возвращён', ROUTED_HUB: 'ушёл в хаб',
};
const FILTER_TEXT: Record<string, string> = {
  distance: 'Расстояние', zone: 'Зона плотности', size: 'Габарит', space: 'Место в ПВЗ',
  time: 'Срок', price: 'Цена покупателя', trip: 'Окупаемость рейса',
};

/** Карточка решения: режим, цена и срок mesh против хаба, таблица фильтров с цифрами. */
export function DecisionCard({ order }: { order: Order }) {
  const failed = order.filters.filter((f) => !f.ok).map((f) => FILTER_TEXT[f.name] ?? f.name);
  return (
    <Card size="small">
      <Flex gap={12} align="center" style={{ marginBottom: 12 }}>
        <ModeBadge mode={order.mode} />
        <Typography.Text strong>
          Заказ {order.order_id}: {MODE_TEXT[order.mode] ?? '—'}, {STATUS_TEXT[order.status] ?? order.status}
        </Typography.Text>
      </Flex>
      <Row gutter={[16, 8]}>
        <Col xs={12} md={6}><Statistic title="Себестоимость mesh" value={formatRub(order.cost_mesh)} /></Col>
        <Col xs={12} md={6}><Statistic title="Себестоимость через хаб" value={formatRub(order.cost_hub)} /></Col>
        <Col xs={12} md={6}><Statistic title="Срок mesh" value={formatHours(order.eta_mesh_h, 0)} /></Col>
        <Col xs={12} md={6}><Statistic title="Срок через хаб" value={formatHours(order.eta_hub_h, 0)} /></Col>
      </Row>
      {order.filters.length > 0 && (
        <Table
          size="small" pagination={false} style={{ marginTop: 12 }} rowKey="name" dataSource={order.filters}
          columns={[
            { title: '', dataIndex: 'ok', width: 40, render: (ok: boolean) => (ok ? '✅' : '❌') },
            { title: 'Фильтр', dataIndex: 'name', width: 200, render: (n: string) => FILTER_TEXT[n] ?? n },
            { title: 'Значение', dataIndex: 'value' },
          ]}
        />
      )}
      {failed.length > 0 && <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>Не прошли: {failed.join(', ')}</Typography.Paragraph>}
      {order.mode === 'B' && order.status === 'RESERVED' && (
        <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
          Режим B предварительный: окончательно подтверждается при формировании рейса.
        </Typography.Paragraph>
      )}
    </Card>
  );
}
