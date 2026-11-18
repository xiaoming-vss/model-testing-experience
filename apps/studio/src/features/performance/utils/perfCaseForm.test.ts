import { describe, expect, it } from 'vitest'
import {
  createPerfDataEntry,
  createPerfStep,
  perfCaseFormErrors,
  readPerfCaseForm,
  updatePerfCaseInYaml,
  variablesBeforeStep,
} from './perfCaseForm'

const SOURCE_YAML = `specVersion: "1.0"
case:
  name: 登录并校验
  data:
    - name: users
      source: users.csv
      strategy: unique_per_iteration
      onExhausted: cycle
  steps:
    - name: login
      method: POST
      path: /login
      headers:
        Content-Type: application/json
      body:
        username: "{{data.username}}"
        password: "{{data.password}}"
      checks:
        - type: status
          op: eq
          value: 200
        - type: json
          path: code
          op: eq
          value: 0
      extract:
        - name: token
          from: json
          path: data.token
    - name: profile
      method: GET
      path: /profile
      headers:
        Authorization: "Bearer {{var.token}}"
      onFailure: continue
      thinkTimeMs: 200
      checks:
        - type: status
          op: eq
          value: 200
  load:
    model: vus
    vus: 20
    duration: "60s"
  acceptance:
    source: user_confirmed
    confirmed: true
    criteria:
      http_req_failed: ["rate<0.01"]
`

const SUMMARY = { name: '登录并校验' }

describe('performance case form', () => {
  it('reads steps, headers, body, checks, extract, data, and load', () => {
    const form = readPerfCaseForm(SOURCE_YAML, SUMMARY)
    expect(form).not.toBeNull()
    expect(form).toMatchObject({
      name: '登录并校验',
      load: { model: 'vus', vus: 20, durationSeconds: 60 },
    })
    expect(form!.steps).toHaveLength(2)
    expect(form!.steps[0]).toMatchObject({
      name: 'login',
      method: 'POST',
      path: '/login',
      bodyMode: 'json',
      bodyContentType: 'json',
      onFailure: 'abort_iteration',
    })
    expect(form!.steps[0].headers[0]).toMatchObject({ name: 'Content-Type', value: 'application/json' })
    expect(form!.steps[0].checks).toHaveLength(2)
    expect(form!.steps[0].checks[1]).toMatchObject({ type: 'json', path: 'code', op: 'eq', value: '0' })
    expect(form!.steps[0].extract[0]).toMatchObject({ name: 'token', source: 'json', path: 'data.token' })
    expect(form!.steps[1]).toMatchObject({ onFailure: 'continue', thinkTimeMs: 200 })
    expect(form!.data[0]).toMatchObject({ name: 'users', source: 'users.csv', strategy: 'unique_per_iteration' })
  })

  it('writes steps and data back without removing acceptance', () => {
    const form = readPerfCaseForm(SOURCE_YAML, SUMMARY)!
    form.name = '新的用例名'
    form.steps[1].path = '/v2/profile'
    form.steps[1].bodyMode = 'json'
    form.steps[1].bodyText = '{"ok": true}'
    form.data[0].strategy = 'random'
    const updated = updatePerfCaseInYaml(SOURCE_YAML, form)
    expect(updated).toContain('name: 新的用例名')
    expect(updated).toContain('path: /v2/profile')
    expect(updated).toContain('acceptance:')
    expect(updated).toContain('strategy: random')
    const roundTrip = readPerfCaseForm(updated, { ...SUMMARY, name: '新的用例名' })
    expect(roundTrip).not.toBeNull()
    expect(roundTrip!.steps[1].bodyMode).toBe('json')
    expect(roundTrip!.steps[1].bodyText).toContain('"ok": true')
    expect(roundTrip!.data[0].strategy).toBe('random')
  })

  it('keeps text bodies and omitted bodies intact', () => {
    const form = readPerfCaseForm(SOURCE_YAML, SUMMARY)!
    form.steps[0].bodyMode = 'text'
    form.steps[0].bodyText = 'hello'
    form.steps[1].bodyMode = 'none'
    const updated = updatePerfCaseInYaml(SOURCE_YAML, form)
    expect(updated).toContain('contentType: text')
    expect(updated).toContain('body: hello')
    const roundTrip = readPerfCaseForm(updated, SUMMARY)!
    expect(roundTrip.steps[0].bodyMode).toBe('text')
    expect(roundTrip.steps[1].bodyMode).toBe('none')
  })

  it('shows variables extracted by previous steps only', () => {
    const form = readPerfCaseForm(SOURCE_YAML, SUMMARY)!
    expect(variablesBeforeStep(form.steps, 0)).toEqual([])
    expect(variablesBeforeStep(form.steps, 1)).toEqual(['token'])
    expect(variablesBeforeStep(form.steps, 2)).toEqual(['token'])
  })

  it('reports invalid step, body, extract, and request-rate combinations', () => {
    const form = readPerfCaseForm(SOURCE_YAML, SUMMARY)!
    form.steps[0].bodyMode = 'json'
    form.steps[0].bodyText = '{broken'
    form.steps[0].extract[0].path = ''
    form.steps[1].name = 'login'
    form.load.model = 'request_rate'
    const errors = perfCaseFormErrors(form)
    expect(errors).toContain('固定请求速率只支持单步骤迭代')
    expect(errors).toContain('步骤 1：请求体不是合法 JSON')
    expect(errors).toContain('步骤 1：提取变量 token 缺少路径')
    expect(errors).toContain('步骤 2：步骤名称重复')
  })

  it('creates new step and data entries with safe defaults', () => {
    expect(createPerfStep()).toMatchObject({ method: 'GET', path: '/', bodyMode: 'none', onFailure: 'abort_iteration' })
    expect(createPerfDataEntry()).toMatchObject({ strategy: 'unique_per_iteration', onExhausted: 'cycle' })
  })
})
