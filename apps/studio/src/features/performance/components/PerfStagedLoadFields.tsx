import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { Button, InputNumber, Segmented, Tooltip } from 'antd'
import {
  PERF_STAGED_TEMPLATES,
  formatPerfLoadDuration,
  stagedLoadPeakVus,
  stagedLoadPoints,
  stagedLoadTotalSeconds,
  type PerfLoadFormValues,
  type PerfLoadProfile,
  type PerfLoadStage,
} from '../utils/perfLoadModel'
import { PerfLoadCurve } from './PerfLoadCurve'
import { PerfNumericField } from './PerfNumericField'

const PROFILE_OPTIONS = [
  { label: '阶梯', value: 'step' },
  { label: '尖峰', value: 'spike' },
  { label: '自定义', value: 'custom' },
]

const STAGE_GRID = 'grid grid-cols-[36px_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_88px] items-center gap-2 px-2.5'

export function PerfStagedLoadFields({
  value,
  disabled = false,
  onChange,
}: {
  value: PerfLoadFormValues
  disabled?: boolean
  onChange: (patch: Partial<PerfLoadFormValues>) => void
}) {
  const updateStages = (stages: PerfLoadStage[]) => onChange({ stages, profile: 'custom' })

  const updateStage = (index: number, patch: Partial<PerfLoadStage>) => {
    updateStages(value.stages.map((stage, stageIndex) => (
      stageIndex === index ? { ...stage, ...patch } : stage
    )))
  }

  const applyTemplate = (profile: PerfLoadProfile) => {
    if (profile === 'custom') {
      onChange({ profile })
      return
    }
    const template = PERF_STAGED_TEMPLATES[profile]
    onChange({
      profile,
      stages: template.stages.map(stage => ({ ...stage })),
      finalDownSeconds: template.finalDownSeconds,
    })
  }

  const addStage = () => {
    const last = value.stages[value.stages.length - 1]
    updateStages([
      ...value.stages,
      {
        target: Math.max(10, Math.round((last?.target ?? 10) * 2)),
        rampSeconds: 5,
        holdSeconds: 30,
      },
    ])
  }

  const removeStage = (index: number) => {
    updateStages(value.stages.filter((_, stageIndex) => stageIndex !== index))
  }

  const moveStage = (index: number, direction: -1 | 1) => {
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= value.stages.length) return
    const stages = [...value.stages]
    ;[stages[index], stages[targetIndex]] = [stages[targetIndex], stages[index]]
    updateStages(stages)
  }

  const peak = stagedLoadPeakVus(value)
  const total = stagedLoadTotalSeconds(value)
  const points = stagedLoadPoints(value)

  return <div className="mt-4 grid gap-3">
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-app-surface-text-muted">快速模板</span>
      <Segmented
        aria-label="阶段负载模板"
        size="small"
        value={value.profile}
        options={PROFILE_OPTIONS}
        disabled={disabled}
        onChange={next => applyTemplate(next as PerfLoadProfile)}
      />
      <span className="text-[10px] text-app-surface-text-muted">选择模板会生成阶段表，之后仍可手动调整</span>
    </div>

    <div className="overflow-x-auto rounded-lg border border-app-surface-border">
      <div className="min-w-[520px]">
        <div className={`${STAGE_GRID} bg-app-surface-hover py-1.5 text-[10px] font-semibold text-app-surface-text-muted`}>
          <span>阶段</span>
          <span>目标 VUs</span>
          <span>爬坡（秒）</span>
          <span>保持（秒）</span>
          <span />
        </div>
        {value.stages.map((stage, index) => <div key={index} className={`${STAGE_GRID} border-t border-app-surface-border py-1.5`}>
          <span className="grid h-[22px] w-[22px] place-items-center rounded-full bg-app-accent-surface text-[10px] font-semibold text-app-accent">{index + 1}</span>
          <InputNumber
            className="w-full"
            size="small"
            min={1}
            precision={0}
            value={stage.target}
            disabled={disabled}
            aria-label={`阶段 ${index + 1} 目标 VUs`}
            onChange={next => updateStage(index, { target: typeof next === 'number' ? next : stage.target })}
          />
          <InputNumber
            className="w-full"
            size="small"
            min={0}
            precision={0}
            value={stage.rampSeconds}
            disabled={disabled}
            aria-label={`阶段 ${index + 1} 爬坡时间`}
            onChange={next => updateStage(index, { rampSeconds: typeof next === 'number' ? next : stage.rampSeconds })}
          />
          <InputNumber
            className="w-full"
            size="small"
            min={0}
            precision={0}
            value={stage.holdSeconds}
            disabled={disabled}
            aria-label={`阶段 ${index + 1} 保持时间`}
            onChange={next => updateStage(index, { holdSeconds: typeof next === 'number' ? next : stage.holdSeconds })}
          />
          <div className="flex justify-end gap-0.5">
            <Tooltip title="上移阶段">
              <Button
                size="small"
                type="text"
                icon={<ArrowUpOutlined />}
                aria-label="上移阶段"
                disabled={disabled || index === 0}
                onClick={() => moveStage(index, -1)}
              />
            </Tooltip>
            <Tooltip title="下移阶段">
              <Button
                size="small"
                type="text"
                icon={<ArrowDownOutlined />}
                aria-label="下移阶段"
                disabled={disabled || index === value.stages.length - 1}
                onClick={() => moveStage(index, 1)}
              />
            </Tooltip>
            <Tooltip title="删除阶段">
              <Button
                size="small"
                type="text"
                danger
                icon={<DeleteOutlined />}
                aria-label="删除阶段"
                disabled={disabled}
                onClick={() => removeStage(index)}
              />
            </Tooltip>
          </div>
        </div>)}
        {value.stages.length === 0 ? <div className="border-t border-app-surface-border px-3 py-4 text-center text-xs text-app-surface-text-muted">
          还没有阶段，点击下方「添加阶段」开始配置。
        </div> : null}
      </div>
    </div>

    <Button type="dashed" block icon={<PlusOutlined />} disabled={disabled} onClick={addStage}>
      添加阶段
    </Button>

    <div className="flex flex-wrap items-end gap-3">
      <PerfNumericField
        className="w-36"
        label="结束下降（秒）"
        min={0}
        value={value.finalDownSeconds}
        disabled={disabled}
        onChange={finalDownSeconds => onChange({ finalDownSeconds, profile: 'custom' })}
      />
      <span className="pb-1.5 text-[10px] leading-4 text-app-surface-text-muted">
        每行从上一阶段目标过渡到本阶段目标；结束下降填 0 表示最后阶段后直接结束。
      </span>
    </div>

    <div>
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2 text-xs font-medium">
        <span>负载曲线预览</span>
        <span className="text-[10px] font-normal text-app-surface-text-muted">
          峰值 {peak} 个 VU · 总时长 {formatPerfLoadDuration(total)}
        </span>
      </div>
      <PerfLoadCurve points={points} totalSeconds={total} maxVus={peak} />
    </div>
  </div>
}
