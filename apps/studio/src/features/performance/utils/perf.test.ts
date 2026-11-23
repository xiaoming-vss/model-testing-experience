import { describe, expect, it } from 'vitest'
import { buildDefaultPerfYaml, isPerfRunActive, perfMetricsFromSummary } from './perf'

describe('performance utilities', () => {
  it('builds a valid starter YAML with the case name', () => {
    const yaml = buildDefaultPerfYaml('下单链路压测')
    expect(yaml).toContain('specVersion: "1.0"')
    expect(yaml).toContain('name: "下单链路压测"')
    expect(yaml).toContain('model: vus')
    expect(yaml).toContain('source: missing')
  })

  it('quotes YAML-sensitive characters in the starter case name', () => {
    const yaml = buildDefaultPerfYaml('下单: 压测 #1')
    expect(yaml).toContain('name: "下单: 压测 #1"')
  })

  it('extracts k6 summary metrics', () => {
    const summary = {
      metrics: {
        http_reqs: { values: { rate: 18.4, count: 1240 } },
        http_req_duration: { values: { 'p(95)': 47.7, 'p(99)': 83.2 } },
        http_req_failed: { values: { rate: 0 } },
        vus: { values: { value: 2 } },
        iterations: { values: { count: 620 } },
      },
    }
    expect(perfMetricsFromSummary(summary)).toEqual({
      rps: 18.4,
      p95: 47.7,
      p99: 83.2,
      failureRate: 0,
      vus: 2,
      requests: 1240,
      iterations: 620,
    })
  })

  it('recognizes active run states', () => {
    expect(isPerfRunActive('queued')).toBe(true)
    expect(isPerfRunActive('running')).toBe(true)
    expect(isPerfRunActive('stopping')).toBe(true)
    expect(isPerfRunActive('completed')).toBe(false)
    expect(isPerfRunActive(undefined)).toBe(false)
  })
})
