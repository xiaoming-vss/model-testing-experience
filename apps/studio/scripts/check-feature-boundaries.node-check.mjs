import assert from 'node:assert/strict'
import { test } from 'node:test'
import path from 'node:path'
import fs from 'node:fs'
import os from 'node:os'
import { budgetDifferences, budgetIncreases, violations, walk } from './check-feature-boundaries.mjs'

test('detects cross-feature imports, exports and dynamic imports independent of spelling', () => {
  const root = '/app/src/features'
  const file = path.join(root, 'alpha/pages/page.tsx')
  const source = `
    import '../../beta/components/a'
    import x from '@/features/beta/hooks/useX'
    export { y } from '../../beta/utils/y'
    const z = import('../../beta/store/z')
    const template = import(` + "`../../beta/pages/x`" + `)
    const unknown = import(somePath)
    import z = require('/src/features/beta/store/x')
    const a = require('@/features/beta/components/a')
    import * as root from '@/features/beta'
    import { allowed } from '@/features/beta/api'
    import type { T } from '../../beta/types'
    import same from '../components/same'
    // import '../../beta/ignored/comment'
  `
  assert.deepEqual(violations(source, file, root), [
    'beta/components/a', 'beta/hooks/useX', 'beta/utils/y', 'beta/store/z', 'beta/pages/x', '<non-literal module import>', 'beta/store/x', 'beta/components/a', 'beta',
  ])
})

test('requires the baseline to shrink when a violation is removed', () => {
  assert.deepEqual(budgetDifferences({ a: 1 }, { a: 1 }), [])
  assert.deepEqual(budgetDifferences({}, { a: 1 }), ['a: 0 vs 1'])
  assert.deepEqual(budgetDifferences({ a: 2 }, { a: 1 }), ['a: 2 vs 1'])
  assert.deepEqual(budgetIncreases({ a: 1 }, { a: 2 }), [])
  assert.deepEqual(budgetIncreases({ a: 2, b: 1 }, { a: 1 }), ['a', 'b'])
})

test('checks JS and JSX files and distinguishes shared code from the public aggregator', () => {
  const root = '/app/src/features'
  const source = "import x from '@/features/beta/api'; export { y } from '../features/beta/hooks/y'"
  assert.deepEqual(violations(source, '/app/src/shared/view.js', root, { shared: true, allowPublic: false }), ['beta/api', 'beta/hooks/y'])
  assert.deepEqual(violations(source, '/app/src/services/api.ts', root, { shared: true, allowPublic: true }), ['beta/hooks/y'])
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mtx-boundary-'))
  try {
    for (const name of ['view.js', 'view.jsx', 'view.tsx', 'view.test.js']) fs.writeFileSync(path.join(dir, name), '')
    assert.deepEqual(walk(dir).map(file => path.basename(file)).sort(), ['view.js', 'view.jsx', 'view.tsx'])
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
  }
})
