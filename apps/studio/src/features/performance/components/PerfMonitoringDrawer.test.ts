import { describe, expect, it } from 'vitest'
import { buildMonitoringConnectionPayload, type MonitoringConnectionFormValues } from '../utils/monitoringConnection'
import type { MonitoringConnection } from '../types'

const baseValues: MonitoringConnectionFormValues = {
  name: 'K8s Prometheus',
  queryUrl: 'http://prom:9090',
  remoteWriteUrl: 'http://prom:9090/api/v1/write',
  queryAuthType: 'none',
  remoteWriteAuthType: 'none',
  grafanaUrl: '',
  grafanaDashboardUid: '',
  defaultFiltersJson: '',
  enabled: true,
}

const existing: MonitoringConnection = {
  connectionId: 'prom-1',
  projectId: 'project-1',
  name: 'K8s Prometheus',
  queryUrl: 'http://prom:9090',
  remoteWriteUrl: 'http://prom:9090/api/v1/write',
  queryAuthType: 'none',
  remoteWriteAuthType: 'basic',
  hasQueryCredentials: false,
  hasRemoteWriteCredentials: true,
  grafanaUrl: '',
  grafanaDashboardUid: '',
  defaultFilters: {},
  enabled: true,
}

describe('monitoring connection payload', () => {
  it('keeps existing write credentials when the form leaves secrets blank', () => {
    const payload = buildMonitoringConnectionPayload({
      ...baseValues,
      remoteWriteAuthType: 'basic',
      remoteWriteUsername: '',
      remoteWritePassword: '',
    }, existing)
    expect(payload.remoteWriteAuth).toBeUndefined()
    expect(payload.defaultFilters).toEqual({})
  })

  it('sends new credentials when the auth type changes', () => {
    const payload = buildMonitoringConnectionPayload({
      ...baseValues,
      remoteWriteAuthType: 'bearer',
      remoteWriteToken: 'new-token',
    }, existing)
    expect(payload.remoteWriteAuth).toEqual({ type: 'bearer', token: 'new-token' })
  })

  it('requires complete basic credentials for a new connection', () => {
    expect(() => buildMonitoringConnectionPayload({
      ...baseValues,
      queryAuthType: 'basic',
      queryUsername: 'reader',
    }, null)).toThrow('Basic 认证必须填写密码')
  })

  it('parses default filters as a JSON object', () => {
    const payload = buildMonitoringConnectionPayload({
      ...baseValues,
      defaultFiltersJson: '{"namespace":"perf"}',
    }, null)
    expect(payload.defaultFilters).toEqual({ namespace: 'perf' })
  })

  it('rejects a non-object default filter payload', () => {
    expect(() => buildMonitoringConnectionPayload({
      ...baseValues,
      defaultFiltersJson: '["perf"]',
    }, null)).toThrow('默认筛选必须是 JSON 对象')
  })

  it('turns malformed JSON into a readable validation error', () => {
    expect(() => buildMonitoringConnectionPayload({
      ...baseValues,
      remoteWriteAuthType: 'headers',
      remoteWriteHeadersJson: '{"Authorization":',
    }, null)).toThrow('认证 Headers 必须是 JSON 对象')
  })
})
