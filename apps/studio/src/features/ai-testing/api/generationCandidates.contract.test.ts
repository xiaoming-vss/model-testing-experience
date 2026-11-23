import { expect, it } from 'vitest'
import type { AdoptionCheck, CandidateAdoptBody, CandidateRunBody } from './generationCandidates.contract'

it('keeps trial selection separate from adoption', () => {
  const trial = {
    connectionId: 'connection-1',
    generationMode: 'trial',
    sourceSelections: [{
      chainKind: 'function',
      stage: 'case_names',
      sourceKind: 'candidate',
      candidateId: 'candidate-a',
      snapshotId: 'snapshot-a',
      expectedCandidateToken: 'token-a',
    }],
  } satisfies CandidateRunBody
  const blocked = {
    canAdopt: false,
    lineageHash: 'sha256:lineage',
    blockingSources: [{ chainKind: 'function', stage: 'case_names', reason: 'source_conflict' }],
  } satisfies AdoptionCheck
  const adopt = {
    action: 'adopt',
    candidateId: 'candidate-a',
    expectedCandidateToken: 'token-a',
    expectedAttemptId: 'attempt-a',
    expectedCurrentToken: 'current-token',
    requestId: '40b5b45c-c03d-4e2a-9957-8e76f7db3f46',
  } satisfies CandidateAdoptBody

  expect(trial.generationMode).toBe('trial')
  expect(blocked.blockingSources[0].reason).toBe('source_conflict')
  expect(adopt.action).toBe('adopt')
})
