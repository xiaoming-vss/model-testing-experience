import type { HeaderPreset } from './RequestHeaderToolbar'

export const requestHeaderPresets: readonly HeaderPreset[] = [
  { label: 'Content-Type', key: 'Content-Type', value: 'application/json' },
  { label: 'Authorization', key: 'Authorization', value: '' },
  { label: 'Accept: application/json', key: 'Accept', value: 'application/json' },
  { label: 'X-Request-ID', key: 'X-Request-ID', value: '' },
  { label: 'User-Agent', key: 'User-Agent', value: '' },
  { label: 'X-Tenant', key: 'X-Tenant', value: '{{env.tenant}}' },
]

