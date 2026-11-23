import { expect, it, vi } from 'vitest'
import { request } from '@/shared/api/request'
import { generationCandidatesApi } from './generationCandidates.api'

vi.mock('@/shared/api/request', async importOriginal => {
  const actual = await importOriginal<typeof import('@/shared/api/request')>()
  return { ...actual, request: vi.fn() }
})

it('候选列表分页并按需求、阶段及候选身份请求详情', async () => {
  vi.mocked(request).mockResolvedValue({} as never)
  await generationCandidatesApi.list('req 1', 'function', 'case_names', 2, 10)
  expect(request).toHaveBeenLastCalledWith('/v1/requirements/req%201/generation/function/stages/case_names/candidates?page=2&pageSize=10')
  await generationCandidatesApi.detail('req 1', 'function', 'case_names', 'candidate/a')
  expect(request).toHaveBeenLastCalledWith('/v1/requirements/req%201/generation/function/stages/case_names/candidates/candidate%2Fa')
  const body = { action: 'reject', expectedCandidateToken: 'token', requestId: 'request' } as const
  await generationCandidatesApi.dispose('req 1', 'function', 'case_names', 'candidate-a', body)
  expect(request).toHaveBeenLastCalledWith('/v1/requirements/req%201/generation/function/stages/case_names/candidates/candidate-a/disposition', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  const editBody = { expectedCandidateToken: 'token', expectedAttemptId: 'attempt', content: 'new content' }
  await generationCandidatesApi.edit('req 1', 'function', 'case_names', 'candidate-a', editBody)
  expect(request).toHaveBeenLastCalledWith('/v1/requirements/req%201/generation/function/stages/case_names/candidates/candidate-a', {
    method: 'PUT',
    body: JSON.stringify(editBody),
  })
  const deriveBody = { ...editBody, requestId: 'request' }
  await generationCandidatesApi.derive('req 1', 'function', 'case_names', 'candidate-a', deriveBody)
  expect(request).toHaveBeenLastCalledWith('/v1/requirements/req%201/generation/function/stages/case_names/candidates/candidate-a/derive', {
    method: 'POST',
    body: JSON.stringify(deriveBody),
  })
})

it('候选工作流使用当前内容、明确来源和预览令牌', async () => {
  vi.mocked(request).mockResolvedValue({} as never)
  const base = '/v1/requirements/req%201/generation/function'
  await generationCandidatesApi.initialize('req 1', 'function', 'task-a')
  expect(request).toHaveBeenLastCalledWith(`${base}/candidate-chain`, {
    method: 'POST', body: JSON.stringify({ taskId: 'task-a' }),
  })
  await generationCandidatesApi.current('req 1', 'function', 'case_names')
  expect(request).toHaveBeenLastCalledWith(`${base}/stages/case_names/current`)
  const run = { connectionId: 'llm', generationMode: 'trial' as const, sourceSelections: [] }
  await generationCandidatesApi.run('req 1', 'function', 'case_names', run)
  expect(request).toHaveBeenLastCalledWith(`${base}/stages/case_names/candidate-run`, {
    method: 'POST', body: JSON.stringify(run),
  })
  const preview = { expectedCurrentToken: 'current', targetId: 'suite' }
  await generationCandidatesApi.previewImport('req 1', 'function', 'detailed_cases', preview)
  expect(request).toHaveBeenLastCalledWith(`${base}/stages/detailed_cases/current/import-preview`, {
    method: 'POST', body: JSON.stringify(preview),
  })
})
