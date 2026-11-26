import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { ESLint } from 'eslint'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BUDGET = path.join(ROOT, 'scripts/size-budget.json')
const DEFAULT_LINES = 400
const DEFAULT_LINES_TS = 300
const DEFAULT_FUNCTION_LINES = 150
const update = process.argv.includes('--update')

const budget = JSON.parse(readFileSync(BUDGET, 'utf8')).files
const eslint = new ESLint({
  cwd: ROOT,
  overrideConfig: [{
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/**/*.test.{ts,tsx}', 'src/**/__fixtures__/**'],
    rules: {
      'max-lines': ['error', { max: 0, skipBlankLines: true, skipComments: true }],
      'max-lines-per-function': ['error', { max: 0, skipBlankLines: true, skipComments: true }],
    },
  }],
})
const results = await eslint.lintFiles(['src/**/*.{ts,tsx}'])
const actual = new Map()
for (const result of results) {
  const relative = path.relative(ROOT, result.filePath).split(path.sep).join('/')
  if (result.fatalErrorCount) {
    console.error(`Size budget check failed: cannot parse ${relative}`)
    process.exit(1)
  }
  let maxLines = 0
  let maxLinesPerFunction = 0
  for (const message of result.messages) {
    const match = message.message.match(/\((\d+)\)/)
    if (!match) continue
    if (message.ruleId === 'max-lines') maxLines = Number(match[1])
    if (message.ruleId === 'max-lines-per-function') {
      maxLinesPerFunction = Math.max(maxLinesPerFunction, Number(match[1]))
    }
  }
  actual.set(relative, { maxLines, maxLinesPerFunction })
}

function defaultLines(file) {
  return file.endsWith('.tsx') ? DEFAULT_LINES : DEFAULT_LINES_TS
}

function limitsFor(file) {
  return {
    maxLines: defaultLines(file),
    maxLinesPerFunction: DEFAULT_FUNCTION_LINES,
  }
}

function entryFor(file) {
  const measured = actual.get(file) ?? { maxLines: 0, maxLinesPerFunction: 0 }
  const defaults = limitsFor(file)
  const entry = {}
  if (measured.maxLinesPerFunction > defaults.maxLinesPerFunction) {
    entry.maxLinesPerFunction = measured.maxLinesPerFunction
  }
  if (measured.maxLines > defaults.maxLines) entry.maxLines = measured.maxLines
  return entry
}

if (update) {
  const next = {}
  const errors = []
  for (const [file] of actual) {
    const entry = entryFor(file)
    if (!Object.keys(entry).length) continue
    const previous = budget[file]
    if (!previous) {
      errors.push(`${file}: new over-limit file; refactor it instead of adding a baseline entry`)
      continue
    }
    if ((entry.maxLines ?? 0) > (previous.maxLines ?? 0)) {
      errors.push(`${file}: maxLines ${previous.maxLines} -> ${entry.maxLines}`)
    }
    if ((entry.maxLinesPerFunction ?? 0) > (previous.maxLinesPerFunction ?? 0)) {
      errors.push(`${file}: maxLinesPerFunction ${previous.maxLinesPerFunction} -> ${entry.maxLinesPerFunction}`)
    }
    next[file] = entry
  }
  for (const file of Object.keys(budget)) {
    if (!actual.has(file)) errors.push(`${file}: baseline entry no longer exists`)
  }
  if (errors.length) {
    console.error('Size baseline cannot be updated:')
    for (const error of errors) console.error(`  - ${error}`)
    process.exit(1)
  }
  const ordered = Object.fromEntries(Object.entries(next).sort(([a], [b]) => a.localeCompare(b)))
  writeFileSync(BUDGET, `${JSON.stringify({ files: ordered }, null, 2)}\n`)
  console.log(`Size baseline updated: ${Object.keys(ordered).length} files`)
  process.exit(0)
}

const errors = []
const seen = new Set()
for (const [file, frozen] of Object.entries(budget)) {
  const measured = actual.get(file)
  if (!measured) {
    errors.push(`${file}: baseline entry no longer exists`)
    continue
  }
  seen.add(file)
  const defaults = limitsFor(file)
  for (const rule of ['maxLines', 'maxLinesPerFunction']) {
    const defaultLimit = rule === 'maxLines' ? defaults.maxLines : defaults.maxLinesPerFunction
    const frozenValue = frozen[rule]
    const measuredValue = measured[rule]
    if (frozenValue === undefined) {
      if (measuredValue > defaultLimit) {
        errors.push(`${file}: ${rule} ${measuredValue} exceeds ${defaultLimit} without a baseline entry`)
      }
      continue
    }
    if (measuredValue > frozenValue) {
      errors.push(`${file}: ${rule} ${frozenValue} -> ${measuredValue} (increase over frozen baseline)`)
    } else if (measuredValue < frozenValue) {
      errors.push(`${file}: ${rule} ${frozenValue} -> ${measuredValue} (baseline can be lowered; run with --update)`)
    }
    if (measuredValue <= defaultLimit) {
      errors.push(`${file}: ${rule} no longer exceeds ${defaultLimit}; remove it from the baseline with --update`)
    }
  }
}
for (const [file, measured] of actual) {
  if (seen.has(file)) continue
  const defaults = limitsFor(file)
  if (measured.maxLines > defaults.maxLines || measured.maxLinesPerFunction > defaults.maxLinesPerFunction) {
    errors.push(`${file}: over the default limits but missing from the baseline`)
  }
}
if (errors.length) {
  console.error('Size budget check failed:')
  for (const error of errors) console.error(`  - ${error}`)
  process.exit(1)
}
console.log(`Size budget OK: ${Object.keys(budget).length} files at their frozen limits`)
