import { Popconfirm } from 'antd'

const TEMPLATES = [
  { name: '标准模板', sections: ['复现步骤', '实际结果', '预期结果', '环境信息'] },
  { name: '崩溃 Crash', sections: ['复现步骤', '崩溃现象', '错误日志 / 堆栈', '预期结果', '环境信息'] },
  { name: '接口异常', sections: ['接口地址与请求方法', '请求参数 / 请求体', '复现步骤', '实际响应（状态码 / 响应体）', '预期响应', '环境信息'] },
]

export function BugDescriptionTemplates({ value, onChange }: { value: string; onChange: (html: string) => void }) {
  const document = new DOMParser().parseFromString(value, 'text/html')
  const hasContent = Boolean(document.body.textContent?.trim() || document.querySelector('img,video,audio,iframe,hr,table'))
  return <div className="bug-description-templates" role="group" aria-label="描述模板预置">
    <span>模板预置：</span>
    {TEMPLATES.map((template) => {
      const apply = () => onChange(template.sections.map((section) => `<p><strong>【${section}】</strong></p><p></p>`).join(''))
      return <Popconfirm key={template.name} title="替换当前描述？"
        description="当前文字和内嵌截图将被模板替换，附件不受影响。"
        okText="替换" cancelText="保留原内容" disabled={!hasContent} onConfirm={apply}>
        <button type="button" onClick={() => { if (!hasContent) apply() }}>{template.name}</button>
      </Popconfirm>
    })}
  </div>
}
