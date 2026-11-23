import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(fileURLToPath(import.meta.url))
const featureBoundaryBudget = JSON.parse(
  fs.readFileSync(path.join(root, 'scripts/feature-boundary-budget.json'), 'utf8'),
)
const featureNames = fs.readdirSync(path.join(root, 'src/features'), { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
const boundaryBaselineFiles = [...new Set(Object.keys(featureBoundaryBudget.violations ?? {}).map(key => key.split(' -> ')[0]))]
const featureInternalDirs = [
  'components', 'pages', 'hooks', 'utils', 'styles', 'config', 'constants',
  'store', 'workers', 'fixtures', '__fixtures__',
]
const featureBoundaryMessage = 'Feature 之间只能经 api/ 或 types.ts 通信（STRUCTURE S3）'
function featureBoundaryPatterns(current) {
  return featureNames
    .filter((target) => target !== current)
    .flatMap((target) => [
      `@/features/${target}/index`,
      `@/features/${target}/index.ts`,
      ...featureInternalDirs.map((dir) => `@/features/${target}/${dir}/**`),
    ])
}

export default defineConfig([
  globalIgnores(['dist', '.scratch/**', '.codex-*-preview/**']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      'react-hooks/set-state-in-effect': 'off',
      // 解构时用 rest 剔除不传给底层组件的 props 是常见写法，不应算未使用变量。
      '@typescript-eslint/no-unused-vars': ['error', { ignoreRestSiblings: true }],
    },
  },
  {
    // Web Crypto is only exposed in secure contexts (HTTPS/localhost); plain
    // HTTP deployments must go through the shared helpers instead.
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/shared/utils/crypto.ts', 'src/**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-properties': ['error',
        { object: 'crypto', property: 'randomUUID', message: '使用 @/shared/utils/crypto 的 randomId()，crypto.randomUUID 在非安全上下文不可用' },
        { object: 'crypto', property: 'subtle', message: '使用 @/shared/utils/crypto 的 sha256Hex()，crypto.subtle 在非安全上下文不可用' },
      ],
    },
  },
  ...featureNames.map((name) => ({
    files: [`src/features/${name}/**/*.{ts,tsx}`],
    ignores: ['**/*.test.{ts,tsx}', '**/__fixtures__/**'],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [{
          group: featureBoundaryPatterns(name),
          message: featureBoundaryMessage,
        }],
      }],
    },
  })),
  {
    // Existing violations are ratcheted by scripts/check-feature-boundaries.mjs.
    files: boundaryBaselineFiles,
    rules: { 'no-restricted-imports': 'off' },
  },
])
