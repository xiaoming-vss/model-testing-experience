import { parseDocument } from 'yaml'
import { toRecord } from '@/shared/utils/value'

export type PerfLoadModel = 'vus' | 'arrival_rate' | 'request_rate' | 'staged_vus'
export type PerfLoadTimeUnit = '1s' | '1m'
export type PerfLoadProfile = 'step' | 'spike' | 'custom'

export type PerfLoadStage = {
  target: number
  rampSeconds: number
  holdSeconds: number
}

export type PerfLoadFormValues = {
  model: PerfLoadModel
  vus: number
  durationSeconds: number
  rampUpSeconds: number
  rampDownSeconds: number
  rate: number
  timeUnit: PerfLoadTimeUnit
  preAllocatedVUs: number
  maxVUs: number
  profile: PerfLoadProfile
  stages: PerfLoadStage[]
  finalDownSeconds: number
}

export type PerfLoadCurvePoint = {
  t: number
  v: number
}

export const PERF_LOAD_MODEL_LABELS: Record<PerfLoadModel, string> = {
  vus: '固定并发',
  arrival_rate: '固定到达率',
  request_rate: '固定请求速率',
  staged_vus: '阶段负载',
}

export const PERF_LOAD_PROFILE_LABELS: Record<PerfLoadProfile, string> = {
  step: '阶梯',
  spike: '尖峰',
  custom: '阶段负载',
}

type PerfStagedTemplate = {
  stages: PerfLoadStage[]
  finalDownSeconds: number
}

export const PERF_STAGED_TEMPLATES: Record<Exclude<PerfLoadProfile, 'custom'>, PerfStagedTemplate> = {
  step: {
    stages: [
      { target: 10, rampSeconds: 5, holdSeconds: 30 },
      { target: 30, rampSeconds: 5, holdSeconds: 30 },
      { target: 60, rampSeconds: 5, holdSeconds: 60 },
    ],
    finalDownSeconds: 10,
  },
  spike: {
    stages: [
      { target: 5, rampSeconds: 0, holdSeconds: 30 },
      { target: 50, rampSeconds: 5, holdSeconds: 10 },
      { target: 5, rampSeconds: 5, holdSeconds: 30 },
    ],
    finalDownSeconds: 0,
  },
}

function cloneStages(stages: PerfLoadStage[]) {
  return stages.map(stage => ({ ...stage }))
}

const DEFAULT_LOAD: PerfLoadFormValues = {
  model: 'vus',
  vus: 10,
  durationSeconds: 60,
  rampUpSeconds: 0,
  rampDownSeconds: 0,
  rate: 10,
  timeUnit: '1s',
  preAllocatedVUs: 2,
  maxVUs: 20,
  profile: 'step',
  stages: cloneStages(PERF_STAGED_TEMPLATES.step.stages),
  finalDownSeconds: PERF_STAGED_TEMPLATES.step.finalDownSeconds,
}

function positiveInt(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.round(value) : fallback
}

export function parsePerfDurationSeconds(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.max(0, value)
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (!text) return null
  const parts = Array.from(text.matchAll(/(\d+(?:\.\d+)?)(ms|s|m|h)/gi))
  if (parts.length === 0 || parts.map(part => part[0]).join('') !== text) return null
  return parts.reduce((total, part) => {
    const amount = Number(part[1])
    const unit = part[2].toLowerCase()
    const factor = unit === 'ms' ? 0.001 : unit === 's' ? 1 : unit === 'm' ? 60 : 3600
    return total + amount * factor
  }, 0)
}

function formatDuration(seconds: number) {
  return `${Math.max(0, Math.round(seconds))}s`
}

export function formatPerfLoadDuration(seconds: number) {
  const total = Math.max(0, Math.round(seconds))
  if (total < 60) return `${total}s`
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return rest ? `${minutes}m${rest}s` : `${minutes}m`
}

function parseYamlRoot(yamlText: string): Record<string, unknown> | null {
  try {
    const document = parseDocument(yamlText)
    if (document.errors.length > 0) return null
    return toRecord(document.toJS())
  } catch {
    return null
  }
}

function readStages(value: unknown): PerfLoadStage[] {
  if (!Array.isArray(value)) return []
  return value.flatMap(item => {
    const stage = toRecord(item)
    if (!stage) return []
    return [{
      target: positiveInt(stage.target, 1),
      rampSeconds: parsePerfDurationSeconds(stage.ramp) ?? 0,
      holdSeconds: parsePerfDurationSeconds(stage.hold) ?? 0,
    }]
  })
}

export function readPerfLoadFromYaml(yamlText: string): PerfLoadFormValues | null {
  const root = parseYamlRoot(yamlText)
  const caseNode = toRecord(root?.case)
  const load = toRecord(caseNode?.load)
  if (!load) return null

  const model = load.model === 'arrival_rate'
    || load.model === 'request_rate'
    || load.model === 'staged_vus'
    || load.model === 'vus'
    ? load.model
    : null
  if (!model) return null

  const staged = model === 'staged_vus'
  return {
    ...DEFAULT_LOAD,
    model,
    vus: positiveInt(load.vus, DEFAULT_LOAD.vus),
    durationSeconds: parsePerfDurationSeconds(load.duration) ?? DEFAULT_LOAD.durationSeconds,
    rampUpSeconds: parsePerfDurationSeconds(load.rampUp) ?? 0,
    rampDownSeconds: parsePerfDurationSeconds(load.rampDown) ?? 0,
    rate: positiveInt(load.rate, DEFAULT_LOAD.rate),
    timeUnit: load.timeUnit === '1m' ? '1m' : '1s',
    preAllocatedVUs: positiveInt(load.preAllocatedVUs ?? load.pre_allocated_vus, DEFAULT_LOAD.preAllocatedVUs),
    maxVUs: positiveInt(load.maxVUs ?? load.max_vus, DEFAULT_LOAD.maxVUs),
    profile: staged && (load.profile === 'step' || load.profile === 'spike' || load.profile === 'custom')
      ? load.profile
      : staged ? 'custom' : DEFAULT_LOAD.profile,
    stages: staged ? readStages(load.stages) : cloneStages(DEFAULT_LOAD.stages),
    finalDownSeconds: staged ? parsePerfDurationSeconds(load.finalDown) ?? 0 : DEFAULT_LOAD.finalDownSeconds,
  }
}

export function serializePerfLoad(values: PerfLoadFormValues): Record<string, unknown> {
  if (values.model === 'staged_vus') {
    return {
      model: 'staged_vus',
      profile: values.profile,
      stages: values.stages.map(stage => ({
        target: Math.max(1, Math.round(stage.target)),
        ramp: formatDuration(stage.rampSeconds),
        hold: formatDuration(stage.holdSeconds),
      })),
      finalDown: formatDuration(values.finalDownSeconds),
    }
  }

  const load: Record<string, unknown> = {
    model: values.model,
    duration: formatDuration(values.durationSeconds),
  }
  if (values.model === 'vus') {
    load.vus = Math.max(1, Math.round(values.vus))
    if (values.rampUpSeconds > 0 || values.rampDownSeconds > 0) {
      load.rampUp = formatDuration(values.rampUpSeconds)
      load.rampDown = formatDuration(values.rampDownSeconds)
    }
    return load
  }
  load.rate = Math.max(1, Math.round(values.rate))
  load.timeUnit = values.timeUnit
  load.preAllocatedVUs = Math.max(1, Math.round(values.preAllocatedVUs))
  load.maxVUs = Math.max(1, Math.round(values.maxVUs))
  return load
}

export function updatePerfLoadInYaml(yamlText: string, values: PerfLoadFormValues): string {
  try {
    const document = parseDocument(yamlText)
    if (document.errors.length > 0) return yamlText
    document.setIn(['case', 'load'], serializePerfLoad(values))
    return document.toString({ indent: 2, lineWidth: 0 }).trimEnd()
  } catch {
    return yamlText
  }
}

export function countPerfStepsFromYaml(yamlText: string): number {
  const caseNode = toRecord(parseYamlRoot(yamlText)?.case)
  return Array.isArray(caseNode?.steps) ? caseNode.steps.length : 0
}

export function stagedLoadPeakVus(values: PerfLoadFormValues) {
  if (values.stages.length === 0) return 0
  return Math.max(...values.stages.map(stage => Math.max(0, Math.round(stage.target))))
}

export function stagedLoadTotalSeconds(values: PerfLoadFormValues) {
  const stageSeconds = values.stages.reduce(
    (total, stage) => total + Math.max(0, stage.rampSeconds) + Math.max(0, stage.holdSeconds),
    0,
  )
  return stageSeconds + Math.max(0, values.finalDownSeconds)
}

export function stagedLoadPoints(values: PerfLoadFormValues): PerfLoadCurvePoint[] {
  const points: PerfLoadCurvePoint[] = [{ t: 0, v: 0 }]
  let t = 0
  for (const stage of values.stages) {
    t += Math.max(0, stage.rampSeconds)
    const target = Math.max(0, stage.target)
    points.push({ t, v: target })
    t += Math.max(0, stage.holdSeconds)
    points.push({ t, v: target })
  }
  if (values.finalDownSeconds > 0) {
    t += Math.max(0, values.finalDownSeconds)
    points.push({ t, v: 0 })
  }
  return points
}

export function formatPerfLoadSummary(values: PerfLoadFormValues): string {
  if (values.model === 'staged_vus') {
    return `${PERF_LOAD_PROFILE_LABELS[values.profile]} · ${values.stages.length} 个阶段，峰值 ${stagedLoadPeakVus(values)} 个 VU，总时长 ${formatPerfLoadDuration(stagedLoadTotalSeconds(values))}`
  }
  const duration = `持续 ${Math.max(0, Math.round(values.durationSeconds))}s`
  if (values.model === 'vus') {
    const ramp = values.rampUpSeconds > 0 ? `，${Math.round(values.rampUpSeconds)}s 内爬坡` : ''
    return `${Math.max(1, Math.round(values.vus))} 个 VU，${duration}${ramp}`
  }
  const unit = values.timeUnit === '1m' ? 'min' : 's'
  const rate = Math.max(1, Math.round(values.rate))
  return values.model === 'arrival_rate'
    ? `${rate} 次/${unit}，${duration}`
    : `${rate} 请求/${unit}，${duration}`
}

export function perfLoadFormError(values: PerfLoadFormValues, stepCount: number): string {
  if (values.model === 'staged_vus') {
    if (values.stages.length === 0) return '至少添加一个阶段'
    if (values.stages.some(stage => stage.target <= 0)) return '阶段目标 VUs 必须大于 0'
    if (values.stages.some(stage => stage.rampSeconds < 0 || stage.holdSeconds < 0)) {
      return '阶段爬坡和保持时间不能为负数'
    }
    if (values.finalDownSeconds < 0) return '结束下降时间不能为负数'
    return ''
  }
  if (values.durationSeconds <= 0) return '持续时间必须大于 0'
  if (values.model === 'vus' && values.vus <= 0) return 'VUs 必须大于 0'
  if (values.model === 'arrival_rate' || values.model === 'request_rate') {
    if (values.rate <= 0) return '速率必须大于 0'
    if (values.maxVUs < values.preAllocatedVUs) return '最大 VUs 不能小于预分配 VUs'
  }
  if (values.model === 'request_rate' && stepCount > 1) return '固定请求速率只支持单步骤迭代'
  return ''
}

export const PERF_LOAD_DEFAULTS = DEFAULT_LOAD
