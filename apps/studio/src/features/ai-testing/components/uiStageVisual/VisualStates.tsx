import { Alert, Button, Empty } from 'antd'

export function VisualEmpty({ title, description, onShowRaw }: { title: string; description: string; onShowRaw: () => void }) {
  return <div className="uisv-state flex h-full flex-col items-center justify-center gap-2.5 text-center [&_.ant-empty]:m-0">
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<div className="uisv-state-copy flex flex-col gap-[3px]"><strong className="text-[13px] text-[var(--uisv-334155)]">{title}</strong><span className="text-[11px] text-[var(--uisv-94a3b8)]">{description}</span></div>} />
    <Button size="small" onClick={onShowRaw}>查看原文</Button>
  </div>
}

export function VisualParseError({ label, onShowRaw }: { label: string; onShowRaw: () => void }) {
  return <div className="uisv-state uisv-state-error flex h-full flex-col items-center justify-center gap-2.5 text-center [&_.ant-alert]:max-w-[520px] [&_.ant-alert]:text-left [&_.ant-empty]:m-0">
    <Alert showIcon type="warning" title={`${label} 暂时无法解析`} description="内容可能是正在编辑的中间态，或不是合法的 JSON/YAML。请切换到原文视图检查。" />
    <Button size="small" type="primary" onClick={onShowRaw}>切换到原文</Button>
  </div>
}
