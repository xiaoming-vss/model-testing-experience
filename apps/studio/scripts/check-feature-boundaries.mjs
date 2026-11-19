import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FEATURES = path.join(ROOT, 'src', 'features')
const BUDGET = path.join(ROOT, 'scripts', 'feature-boundary-budget.json')
const IMPORT_PATTERN = /(?:from\s+|import\(\s*)['"]@\/features\/([^/'"]+)\/([^'"]+)['"]/g

function walk(dir) {
  const files = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === '__fixtures__') continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) files.push(...walk(full))
    else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.(ts|tsx)$/.test(entry.name)) files.push(full)
  }
  return files
}

const current = {}
for (const file of walk(FEATURES)) {
  const relative = path.relative(ROOT, file).split(path.sep).join('/')
  const currentFeature = relative.split('/')[2]
  const source = fs.readFileSync(file, 'utf8')
  let count = 0
  for (const match of source.matchAll(IMPORT_PATTERN)) {
    const [, target, rest] = match
    if (target === currentFeature) continue
    if (rest === 'api' || rest.startsWith('api/')) continue
    if (rest === 'types' || rest === 'types.ts') continue
    count += 1
  }
  if (count > 0) current[relative] = count
}

const total = Object.values(current).reduce((sum, value) => sum + value, 0)
if (process.argv.includes('--update')) {
  const ordered = Object.fromEntries(Object.entries(current).sort(([a], [b]) => a.localeCompare(b)))
  fs.writeFileSync(BUDGET, `${JSON.stringify({ total, files: ordered }, null, 2)}\n`)
  console.log(`Feature boundary budget updated: ${total} violations in ${Object.keys(ordered).length} files`)
  process.exit(0)
}

if (!fs.existsSync(BUDGET)) {
  console.error('Missing scripts/feature-boundary-budget.json; run with --update after reviewing violations')
  process.exit(1)
}
const budget = JSON.parse(fs.readFileSync(BUDGET, 'utf8'))
const failures = []
for (const [file, count] of Object.entries(current)) {
  const allowed = budget.files?.[file] ?? 0
  if (count > allowed) failures.push(`${file}: ${count} > ${allowed}`)
}
if (total > (budget.total ?? 0)) failures.push(`total: ${total} > ${budget.total ?? 0}`)
if (failures.length > 0) {
  console.error('New cross-feature internal imports detected:')
  for (const failure of failures) console.error(`  ${failure}`)
  console.error('Use @/features/<feature>/api or /types instead, or update the budget after review.')
  process.exit(1)
}
console.log(`Feature boundaries OK: ${total} existing violations within budget`)
