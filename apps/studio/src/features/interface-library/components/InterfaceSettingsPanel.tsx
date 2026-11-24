import {
  RightOutlined,
  EditOutlined,
  FileTextOutlined,
  KeyOutlined,
} from '@ant-design/icons'
import { Input, Select } from 'antd'
import { InterfaceFieldLabel } from './InterfaceFieldLabel'
import type { RequirementOption } from '@/features/requirements/types'
import type { ApiInterface } from '../types'
import { describeInterfaceAuth } from '../utils/interfaceSecurity'
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

const HINT_CLASS = 'if-field-hint text-[11px] leading-[18px] text-[var(--srf-text-muted)]'
const META_ROW_CLASS = 'flex items-baseline justify-between gap-3 text-[11px] leading-4'

export function InterfaceSettingsPanel({
  draft,
  readOnly,
  tagsText,
  onTagsText,
  requirementOptions,
  onChange,
}: Props) {
  const sourceType = draft.source.type?.trim() ?? ''
  const sourceName = draft.source.name?.trim() ?? ''
  const sourceVersion = draft.source.version?.trim() ?? ''
  const sourceLabel = SOURCE_LABELS[sourceType] || sourceType || '手工创建'
  const sourceTitle = sourceName || sourceLabel
  const sourceMeta = [
    sourceName ? sourceLabel : '',
    sourceVersion ? `v${sourceVersion}` : '',
  ].filter(Boolean).join(' · ')
  const isManualSource = !sourceType || sourceType === 'manual'
  const SourceIcon = isManualSource ? EditOutlined : FileTextOutlined
  const auth = describeInterfaceAuth(draft.security, draft.securitySchemes)

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
    <div className="@container">
      <div className="if-settings-panel mx-auto grid max-w-[1120px] gap-6 @min-[860px]:grid-cols-[minmax(0,1fr)_300px] @min-[860px]:gap-8">
        <div className="flex min-w-0 flex-col gap-5">
          <label className="if-settings-field flex flex-col gap-1.5">
            <span className="flex items-center justify-between gap-3">
              <InterfaceFieldLabel>接口描述</InterfaceFieldLabel>
              <span
                className="text-[10.5px] leading-4 tabular-nums text-[var(--srf-text-muted)]"
                aria-hidden
              >
                {draft.description.length} / 1024
              </span>
            </span>
            <Input.TextArea
              value={draft.description}
              rows={3}
              maxLength={1024}
              disabled={readOnly}
              placeholder="说明接口用途、业务约束等"
              aria-label="接口描述"
              onChange={event => onChange({ description: event.target.value })}
            />
            <span className={HINT_CLASS}>说明接口用途与业务约束。</span>
          </label>

          <label className="if-settings-field flex flex-col gap-1.5">
            <InterfaceFieldLabel>标签</InterfaceFieldLabel>
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
            <span className={HINT_CLASS}>回车或逗号分隔，用于接口库筛选。</span>
          </label>

          <div className="if-settings-field flex flex-col gap-1.5">
            <InterfaceFieldLabel>关联需求</InterfaceFieldLabel>
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
            <span className={HINT_CLASS}>只关联需求；迭代通过需求归属自动推导。</span>
          </div>
        </div>

        <aside
          className="if-settings-meta min-w-0 border-t border-[var(--srf-divider)] pt-5 @min-[860px]:border-t-0 @min-[860px]:border-l @min-[860px]:pl-7 @min-[860px]:pt-0"
          aria-label="来源与认证"
        >
          <div className="flex items-center justify-between gap-3">
            <h3 className="m-0 text-[12px] font-semibold leading-5 text-[var(--srf-text)]">来源与认证</h3>
            <span className="rounded-full border border-[var(--srf-card-border)] px-2 py-0.5 text-[10px] leading-4 text-[var(--srf-text-muted)]">
              只读
            </span>
          </div>

          <div className="mt-4 flex items-start gap-2.5 border-b border-[var(--srf-divider)] pb-4">
            <span className="grid h-8 w-8 flex-none place-items-center rounded-[8px] border border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)] text-[14px] text-[var(--srf-accent)]">
              <SourceIcon aria-hidden />
            </span>
            <div className="min-w-0">
              <div className="break-words text-[12px] font-semibold leading-[18px] text-[var(--srf-text)]">
                {sourceTitle}
              </div>
              {sourceMeta ? (
                <div className="mt-0.5 text-[10.5px] leading-4 text-[var(--srf-text-muted)]">
                  {sourceMeta}
                </div>
              ) : null}
            </div>
          </div>

          <dl className="mt-4 flex flex-col gap-2.5">
            {draft.source.importedAt ? (
              <div className={META_ROW_CLASS}>
                <dt className="shrink-0 text-[var(--srf-text-muted)]">导入时间</dt>
                <dd className="m-0 min-w-0 text-right text-[var(--srf-text)]">
                  {formatTime(draft.source.importedAt)}
                </dd>
              </div>
            ) : null}
            <div className={META_ROW_CLASS}>
              <dt className="shrink-0 text-[var(--srf-text-muted)]">认证</dt>
              <dd className="m-0 min-w-0 text-right">
                <span
                  className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] leading-4 ${
                    auth.hasAuth
                      ? 'border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)] text-[var(--srf-accent)]'
                      : 'border-[var(--srf-card-border)] bg-[var(--srf-chip)] text-[var(--srf-text-muted)]'
                  }`}
                >
                  <KeyOutlined aria-hidden className="text-[10px]" />
                  <span className="break-words">{auth.label}</span>
                </span>
              </dd>
            </div>
          </dl>
          <p className="mt-2.5 text-[11px] leading-[18px] text-[var(--srf-text-muted)]">{auth.hint}</p>

          {auth.hasAuth ? (
            <details className="group mt-4 border-t border-[var(--srf-divider)] pt-3">
              <summary className="flex cursor-pointer list-none items-center gap-1 text-[11px] font-medium leading-[18px] text-[var(--srf-accent)] [&::-webkit-details-marker]:hidden">
                <RightOutlined
                  aria-hidden
                  className="text-[9px] transition-transform group-open:rotate-90"
                />
                原始安全定义
              </summary>
              <pre className="m-0 mt-2.5 max-h-[220px] overflow-auto whitespace-pre-wrap rounded-[8px] border border-[var(--srf-card-border)] bg-[var(--srf-chip)] px-3 py-2.5 text-[11px] leading-[1.5] text-[var(--srf-text-secondary)] [overflow-wrap:anywhere]">
                {JSON.stringify(
                  { security: draft.security, securitySchemes: draft.securitySchemes },
                  null,
                  2,
                )}
              </pre>
            </details>
          ) : null}
        </aside>
      </div>
    </div>
  )
}
