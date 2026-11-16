import { Input, Select } from 'antd'
import type { RequirementOption } from '@/features/requirements/types'
import type { ApiInterface } from '../types'
import { formatTime } from '@/utils/format'

type Props = {
  draft: ApiInterface
  readOnly: boolean
  tagsText: string
  onTagsText: (value: string) => void
  requirementOptions: RequirementOption[]
  onChange: (patch: Partial<ApiInterface>) => void
}

const SOURCE_LABELS: Record<string, string> = {
  manual: '手工创建',
  openapi_file: 'OpenAPI 文档导入',
  openapi: 'OpenAPI 导入',
  swagger: 'Swagger 导入',
}

export function InterfaceSettingsPanel({
  draft,
  readOnly,
  tagsText,
  onTagsText,
  requirementOptions,
  onChange,
}: Props) {
  const source = draft.source
  const requirementChoices = requirementOptions.map(requirement => ({
    label: `${requirement.name} · ${requirement.sprintName}`,
    value: requirement.requirementId,
  }))
  const knownRequirementIds = new Set(requirementChoices.map(choice => choice.value))
  draft.requirements.forEach(requirement => {
    if (knownRequirementIds.has(requirement.requirementId)) return
    knownRequirementIds.add(requirement.requirementId)
    requirementChoices.push({
      label: `${requirement.name} · ${requirement.sprintName}`,
      value: requirement.requirementId,
    })
  })
  return (
    <div className="if-settings-panel">
      <label className="if-settings-field">
        <span className="if-field-label">接口描述</span>
        <Input.TextArea
          value={draft.description}
          rows={3}
          maxLength={1024}
          disabled={readOnly}
          placeholder="说明接口用途、业务约束等"
          aria-label="接口描述"
          onChange={event => onChange({ description: event.target.value })}
        />
      </label>
      <label className="if-settings-field">
        <span className="if-field-label">标签</span>
        <Input
          value={tagsText}
          disabled={readOnly}
          placeholder="多个标签用逗号分隔，例如：订单, 查询"
          aria-label="接口标签"
          onChange={event => {
            onTagsText(event.target.value)
            onChange({
              tags: event.target.value
                .split(/[,，]/)
                .map(tag => tag.trim())
                .filter(Boolean),
            })
          }}
        />
      </label>
      <div className="if-settings-field">
        <span className="if-field-label">关联需求</span>
        <Select
          mode="multiple"
          allowClear
          aria-label="关联需求"
          placeholder="选择关联需求，可多选"
          disabled={readOnly}
          value={draft.requirements.map(requirement => requirement.requirementId)}
          options={requirementChoices}
          onChange={requirementIds => {
            const byId = new Map([
              ...requirementOptions.map(requirement => [requirement.requirementId, requirement] as const),
              ...draft.requirements.map(requirement => [requirement.requirementId, requirement] as const),
            ])
            onChange({
              requirements: requirementIds.flatMap(requirementId => {
                const requirement = byId.get(requirementId)
                return requirement
                  ? [{
                      requirementId: requirement.requirementId,
                      name: requirement.name,
                      sprintId: requirement.sprintId,
                      sprintName: requirement.sprintName,
                    }]
                  : []
              }),
            })
          }}
        />
        <span className="if-field-hint">只关联需求；迭代通过需求归属自动推导。</span>
      </div>
      <div className="if-settings-field">
        <span className="if-field-label">来源信息</span>
        <dl>
          <div><dt>来源</dt><dd>{SOURCE_LABELS[source.type] ?? source.type ?? '手工创建'}</dd></div>
          {source.name ? <div><dt>文档</dt><dd>{source.name}</dd></div> : null}
          {source.version ? <div><dt>版本</dt><dd>{source.version}</dd></div> : null}
          {source.url ? <div><dt>地址</dt><dd><code>{source.url}</code></dd></div> : null}
          {source.importedAt ? <div><dt>导入时间</dt><dd>{formatTime(source.importedAt)}</dd></div> : null}
          <div><dt>最近更新</dt><dd>{formatTime(draft.updatedAt)}</dd></div>
        </dl>
      </div>
      {draft.security || draft.securitySchemes ? (
        <div className="if-settings-field">
          <span className="if-field-label">认证要求</span>
          <pre className="if-security-json">
            {JSON.stringify(
              { security: draft.security, securitySchemes: draft.securitySchemes },
              null,
              2,
            )}
          </pre>
          <span className="if-field-hint">
            来自 OpenAPI/Swagger 导入，生成 API 用例时用于生成认证头；本期只读。
          </span>
        </div>
      ) : null}
    </div>
  )
}
