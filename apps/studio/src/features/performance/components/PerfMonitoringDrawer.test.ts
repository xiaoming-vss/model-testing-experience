import { describe, expect, it } from 'vitest'
import { buildMonitoringConnectionPayload, type MonitoringConnectionFormValues } from '../utils/monitoringConnection'
import type { MonitoringConnection } from '../types'

const baseValues: MonitoringConnectionFormValues = {
  name: 'K8s Prometheus',
  remoteWriteUrl: 'http://prom:9090/api/v1/write',
  remoteWriteAuthType: 'none',
  enabled: true,
}

const existing: MonitoringConnection = {
  connectionId: 'prom-1',
  projectId: 'project-1',
  name: 'K8s Prometheus',
  remoteWriteUrl: 'http://prom:9090/api/v1/write',
  remoteWriteAuthType: 'basic',
  hasRemoteWriteCredentials: true,
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
      remoteWriteAuthType: 'basic',
      remoteWriteUsername: 'writer',
    }, null)).toThrow('Basic 认证必须填写密码')
  })

  it('only sends the remote write connection fields', () => {
    expect(buildMonitoringConnectionPayload(baseValues, null)).toEqual({
      name: 'K8s Prometheus',
      remoteWriteUrl: 'http://prom:9090/api/v1/write',
      remoteWriteAuth: { type: 'none' },
      enabled: true,
    })
  })

  it('turns malformed JSON into a readable validation error', () => {
    expect(() => buildMonitoringConnectionPayload({
      ...baseValues,
      remoteWriteAuthType: 'headers',
      remoteWriteHeadersJson: '{"Authorization":',
    }, null)).toThrow('认证 Headers 必须是 JSON 对象')
  })
})
