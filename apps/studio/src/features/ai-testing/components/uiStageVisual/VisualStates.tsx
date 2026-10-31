import { Alert, Button, Empty } from 'antd'

export function VisualEmpty({ title, description, onShowRaw }: { title: string; description: string; onShowRaw: () => void }) {
  return <div className="uisv-state">
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<div className="uisv-state-copy"><strong>{title}</strong><span>{description}</span></div>} />
    <Button size="small" onClick={onShowRaw}>查看原文</Button>
  </div>
}

export function VisualParseError({ label, onShowRaw }: { label: string; onShowRaw: () => void }) {
  return <div className="uisv-state uisv-state-error">
    <Alert showIcon type="warning" title={`${label} 暂时无法解析`} description="内容可能是正在编辑的中间态，或不是合法的 JSON/YAML。请切换到原文视图检查。" />
    <Button size="small" type="primary" onClick={onShowRaw}>切换到原文</Button>
  </div>
}
