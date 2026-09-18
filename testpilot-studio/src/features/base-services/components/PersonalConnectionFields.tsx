import { Alert, Select, Space, Typography } from 'antd'
import { normalizeInstanceUrl, personalConnectionForInstance } from '../utils/personalConnections'

export function PersonalConnectionFields({ instances, connections, value, onChange }: {
  instances: string[]
  connections: { connectionId: string; name: string; baseUrl: string; status: string }[]
  value: Record<string, string>
  onChange: (value: Record<string, string>) => void
}) {
  return <Space orientation="vertical" style={{ width: '100%', marginBottom: 12 }}>
    {[...new Set(instances.map(normalizeInstanceUrl))].map(instance => {
      const options = connections.filter(c => c.status === 'active' && normalizeInstanceUrl(c.baseUrl) === instance)
      return <div key={instance}>
        <Typography.Text>本人授权 · {instance || '实例信息缺失'}</Typography.Text>
        <Select aria-label={`本人连接 ${instance}`} style={{ width: '100%' }} placeholder="选择本人的同实例连接" value={personalConnectionForInstance(connections, instance, value[instance])?.connectionId} options={options.map(c => ({ value: c.connectionId, label: c.name }))} onChange={id => onChange({ ...value, [instance]: id })} />
        {!options.length ? <Alert type="info" showIcon title="没有可用的本人授权，请前往基础服务配置同实例连接。" /> : null}
      </div>
    })}
  </Space>
}
