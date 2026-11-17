import { describe, expect, it } from 'vitest'
import {
  buildDefaultPerfYaml,
  buildPerfGrafanaUrl,
  isPerfRunActive,
  perfMetricsFromSummary,
  perfThresholdsFromSummary,
} from './perf'

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

  it('builds a Grafana link with the frozen run window and filters', () => {
    const run = {
      runId: 'run-1',
      startedAt: '2026-11-17T14:30:12Z',
      finishedAt: '2026-11-17T14:31:36Z',
      monitoring: {
        connectionId: 'prom-1',
        name: 'K8s Prometheus',
        queryUrl: 'http://prom:9090',
        remoteWriteUrl: 'http://prom:9090/api/v1/write',
        grafanaUrl: 'https://grafana.example.com/',
        grafanaDashboardUid: 'perf overview',
        defaultFilters: { namespace: 'perf', workload: 'checkout' },
      },
    }
    const url = new URL(buildPerfGrafanaUrl(run))
    expect(url.origin).toBe('https://grafana.example.com')
    expect(url.pathname).toBe('/d/perf%20overview')
    expect(url.searchParams.get('var-run_id')).toBe('run-1')
    expect(url.searchParams.get('from')).toBe(String(Date.parse(run.startedAt)))
    expect(url.searchParams.get('to')).toBe(String(Date.parse(run.finishedAt)))
    expect(url.searchParams.get('var-namespace')).toBe('perf')
    expect(url.searchParams.get('var-workload')).toBe('checkout')
  })

  it('returns no Grafana link without a dashboard uid', () => {
    expect(buildPerfGrafanaUrl({
      runId: 'run-1',
      startedAt: '2026-11-17T14:30:12Z',
      monitoring: {
        connectionId: 'prom-1',
        name: 'prom',
        queryUrl: 'http://prom:9090',
        remoteWriteUrl: 'http://prom:9090/api/v1/write',
        grafanaUrl: 'https://grafana.example.com',
        grafanaDashboardUid: '',
        defaultFilters: {},
      },
    })).toBe('')
  })

  it('extracts k6 summary metrics and thresholds', () => {
    const summary = {
      metrics: {
        http_reqs: { values: { rate: 18.4, count: 1240 } },
        http_req_duration: { values: { 'p(95)': 47.7, 'p(99)': 83.2 } },
        http_req_failed: { values: { rate: 0 } },
        vus: { values: { value: 2 } },
        iterations: { values: { count: 620 } },
        http_req_duration_threshold: {
          thresholds: {
            'p(95)<500': { ok: true },
            'p(99)<1000': { ok: false },
          },
        },
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
    expect(perfThresholdsFromSummary(summary)).toEqual([
      { metric: 'http_req_duration_threshold', expression: 'p(95)<500', passed: true },
      { metric: 'http_req_duration_threshold', expression: 'p(99)<1000', passed: false },
    ])
  })

  it('recognizes active run states', () => {
    expect(isPerfRunActive('queued')).toBe(true)
    expect(isPerfRunActive('running')).toBe(true)
    expect(isPerfRunActive('stopping')).toBe(true)
    expect(isPerfRunActive('completed')).toBe(false)
    expect(isPerfRunActive(undefined)).toBe(false)
  })
})
