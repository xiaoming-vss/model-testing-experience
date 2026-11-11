import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

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
])
