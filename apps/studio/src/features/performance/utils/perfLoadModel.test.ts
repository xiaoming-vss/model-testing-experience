import { describe, expect, it } from 'vitest'
import {
  countPerfStepsFromYaml,
  formatPerfLoadSummary,
  parsePerfDurationSeconds,
  perfLoadFormError,
  readPerfLoadFromYaml,
  stagedLoadPeakVus,
  stagedLoadPoints,
  stagedLoadTotalSeconds,
  updatePerfLoadInYaml,
} from './perfLoadModel'

const SOURCE_YAML = `specVersion: "1.0"
case:
  name: 登录并校验
  steps:
    - name: login
      method: POST
      path: /login
    - name: profile
      method: GET
      path: /profile
  load:
    model: vus
    vus: 20
    duration: "60s"
    rampUp: "10s"
    rampDown: "5s"
`

const STAGED_YAML = `specVersion: "1.0"
case:
  name: 尖峰
  steps:
    - name: ping
      method: GET
      path: /ping
  load:
    model: staged_vus
    profile: spike
    stages:
      - target: 5
        ramp: "0s"
        hold: "30s"
      - target: 50
        ramp: "5s"
        hold: "10s"
      - target: 5
        ramp: "5s"
        hold: "30s"
    finalDown: "0s"
`

describe('performance load model form', () => {
  it('reads the load model and duration fields from YAML', () => {
    expect(readPerfLoadFromYaml(SOURCE_YAML)).toMatchObject({
      model: 'vus',
      vus: 20,
      durationSeconds: 60,
      rampUpSeconds: 10,
      rampDownSeconds: 5,
    })
    expect(countPerfStepsFromYaml(SOURCE_YAML)).toBe(2)
  })

  it('parses compound and millisecond durations', () => {
    expect(parsePerfDurationSeconds('1m30s')).toBe(90)
    expect(parsePerfDurationSeconds('500ms')).toBe(0.5)
    expect(parsePerfDurationSeconds('abc')).toBeNull()
  })

  it('updates only the load node and preserves the rest of the case', () => {
    const load = readPerfLoadFromYaml(SOURCE_YAML)
    expect(load).not.toBeNull()
    const updated = updatePerfLoadInYaml(SOURCE_YAML, {
      ...load!,
      model: 'arrival_rate',
      rate: 15,
      timeUnit: '1m',
      durationSeconds: 120,
      preAllocatedVUs: 3,
      maxVUs: 30,
    })
    expect(readPerfLoadFromYaml(updated)).toMatchObject({
      model: 'arrival_rate',
      rate: 15,
      timeUnit: '1m',
      durationSeconds: 120,
      preAllocatedVUs: 3,
      maxVUs: 30,
    })
    expect(countPerfStepsFromYaml(updated)).toBe(2)
    expect(updated).toContain('name: 登录并校验')
  })

  it('removes ramp fields when both ramp values are zero', () => {
    const load = readPerfLoadFromYaml(SOURCE_YAML)
    const updated = updatePerfLoadInYaml(SOURCE_YAML, {
      ...load!,
      rampUpSeconds: 0,
      rampDownSeconds: 0,
    })
    expect(updated).not.toContain('rampUp')
    expect(readPerfLoadFromYaml(updated)).toMatchObject({ rampUpSeconds: 0, rampDownSeconds: 0 })
  })

  it('formats the current load summary and reports invalid combinations', () => {
    const load = readPerfLoadFromYaml(SOURCE_YAML)!
    expect(formatPerfLoadSummary(load)).toBe('20 个 VU，持续 60s，10s 内爬坡')
    expect(perfLoadFormError(load, 2)).toBe('')
    expect(perfLoadFormError({ ...load, model: 'request_rate', rate: 10 }, 2)).toBe('固定请求速率只支持单步骤迭代')
    expect(perfLoadFormError({ ...load, maxVUs: 1, preAllocatedVUs: 2, model: 'arrival_rate' }, 1)).toBe('最大 VUs 不能小于预分配 VUs')
  })

  it('reads a staged spike load and keeps its stage table', () => {
    const load = readPerfLoadFromYaml(STAGED_YAML)

    expect(load).toMatchObject({
      model: 'staged_vus',
      profile: 'spike',
      finalDownSeconds: 0,
      stages: [
        { target: 5, rampSeconds: 0, holdSeconds: 30 },
        { target: 50, rampSeconds: 5, holdSeconds: 10 },
        { target: 5, rampSeconds: 5, holdSeconds: 30 },
      ],
    })
    expect(stagedLoadPeakVus(load!)).toBe(50)
    expect(stagedLoadTotalSeconds(load!)).toBe(80)
    expect(stagedLoadPoints(load!)).toEqual([
      { t: 0, v: 0 },
      { t: 0, v: 5 },
      { t: 30, v: 5 },
      { t: 35, v: 50 },
      { t: 45, v: 50 },
      { t: 50, v: 5 },
      { t: 80, v: 5 },
    ])
    expect(formatPerfLoadSummary(load!)).toBe('尖峰 · 3 个阶段，峰值 50 个 VU，总时长 1m20s')
  })

  it('round-trips staged load stages through YAML and reports stage errors', () => {
    const load = readPerfLoadFromYaml(STAGED_YAML)!
    const updated = updatePerfLoadInYaml(STAGED_YAML, {
      ...load,
      profile: 'step',
      stages: [
        { target: 10, rampSeconds: 5, holdSeconds: 30 },
        { target: 30, rampSeconds: 5, holdSeconds: 30 },
      ],
      finalDownSeconds: 10,
    })

    expect(readPerfLoadFromYaml(updated)).toMatchObject({
      model: 'staged_vus',
      profile: 'step',
      finalDownSeconds: 10,
      stages: [
        { target: 10, rampSeconds: 5, holdSeconds: 30 },
        { target: 30, rampSeconds: 5, holdSeconds: 30 },
      ],
    })
    expect(perfLoadFormError(load, 1)).toBe('')
    expect(perfLoadFormError({ ...load, stages: [] }, 1)).toBe('至少添加一个阶段')
    expect(perfLoadFormError({
      ...load,
      stages: [{ target: 0, rampSeconds: 0, holdSeconds: 0 }],
    }, 1)).toBe('阶段目标 VUs 必须大于 0')
  })

  it('returns null for invalid YAML or a missing load node', () => {
    expect(readPerfLoadFromYaml('case: [')).toBeNull()
    expect(readPerfLoadFromYaml('specVersion: "1.0"\ncase:\n  steps: []\n')).toBeNull()
  })
})
