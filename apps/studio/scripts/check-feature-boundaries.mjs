import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FEATURES = path.join(ROOT, 'src', 'features')
const BUDGET = path.join(ROOT, 'scripts', 'feature-boundary-budget.json')

export function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    if (entry.name === 'node_modules' || entry.name === '__fixtures__') return []
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return walk(full)
    return /\.(?:[cm]?[jt]s|[jt]sx)$/.test(entry.name) && !/\.(?:test|spec)\.(?:[cm]?[jt]s|[jt]sx)$/.test(entry.name) ? [full] : []
  })
}

// Resolve each literal import to a canonical feature path, regardless of alias or relative spelling.
export function violations(source, filename, featuresDir = FEATURES, { shared = false, allowPublic = true } = {}) {
  const kind = /\.[jt]sx$/.test(filename) ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  const file = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, kind)
  const owner = shared ? null : path.relative(featuresDir, filename).split(path.sep)[0]
  const found = []
  function visit(node) {
    let specifier
    if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(node.expression) && node.expression.text === 'require')) && node.arguments.length === 1 && !ts.isStringLiteral(node.arguments[0]) && !ts.isNoSubstitutionTemplateLiteral(node.arguments[0])) {
      found.push('<non-literal module import>')
    }
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      specifier = node.moduleSpecifier.text
    } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference) && node.moduleReference.expression && ts.isStringLiteral(node.moduleReference.expression)) {
      specifier = node.moduleReference.expression.text
    } else if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(node.expression) && node.expression.text === 'require')) && node.arguments.length === 1 && (ts.isStringLiteral(node.arguments[0]) || ts.isNoSubstitutionTemplateLiteral(node.arguments[0]))) {
      specifier = node.arguments[0].text
    }
    if (specifier) {
      const target = specifier.startsWith('@/features/')
        ? path.resolve(featuresDir, specifier.slice('@/features/'.length))
        : specifier.startsWith('/src/features/') ? path.resolve(featuresDir, specifier.slice('/src/features/'.length))
          : specifier.startsWith('.') ? path.resolve(path.dirname(filename), specifier) : null
      if (target) {
        const parts = path.relative(featuresDir, target).split(path.sep)
        const [feature, ...rest] = parts
        const publicEntry = rest[0] === 'api' || /^types(?:\.ts)?$/.test(rest.join('/'))
        if (feature !== '..' && feature !== owner && (!publicEntry || !allowPublic)) {
          found.push([feature, ...rest].join('/'))
        }
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  return found
}

export function budgetDifferences(current, budget) {
  return [...new Set([...Object.keys(current), ...Object.keys(budget)])]
    .filter(key => (current[key] ?? 0) !== (budget[key] ?? 0))
    .map(key => `${key}: ${current[key] ?? 0} vs ${budget[key] ?? 0}`)
}

export function budgetIncreases(current, budget) {
  return Object.keys(current).filter(key => current[key] > (budget[key] ?? 0))
}

function main() {
  const current = {}
  for (const file of walk(FEATURES)) {
    const relative = path.relative(ROOT, file).split(path.sep).join('/')
    for (const target of violations(fs.readFileSync(file, 'utf8'), file)) {
      const key = `${relative} -> ${target}`
      current[key] = (current[key] ?? 0) + 1
    }
  }
  // S1: shared/domain/utils/services cannot depend on features; the legacy
  // services/api.ts aggregator may only use public feature contracts.
  for (const directory of ['shared', 'domain', 'utils', 'services']) {
    const root = path.join(ROOT, 'src', directory)
    if (!fs.existsSync(root)) continue
    for (const file of walk(root)) {
      const relative = path.relative(ROOT, file).split(path.sep).join('/')
      const allowPublic = relative === 'src/services/api.ts'
      for (const target of violations(fs.readFileSync(file, 'utf8'), file, FEATURES, { shared: true, allowPublic })) {
        const key = `${relative} -> ${target}`
        current[key] = (current[key] ?? 0) + 1
      }
    }
  }
  const ordered = Object.fromEntries(Object.entries(current).sort(([a], [b]) => a.localeCompare(b)))
  if (process.argv.includes('--update')) {
    if (fs.existsSync(BUDGET)) {
      const previous = JSON.parse(fs.readFileSync(BUDGET, 'utf8')).violations
      if (!previous) throw new Error('Feature boundary budget must contain violations')
      const increases = budgetIncreases(current, previous)
      if (increases.length) {
        console.error('Cannot increase the feature boundary baseline:')
        for (const key of increases) console.error(`  ${key}: ${current[key]} > ${previous[key] ?? 0}`)
        process.exitCode = 1
        return
      }
    }
    fs.writeFileSync(BUDGET, `${JSON.stringify({ violations: ordered }, null, 2)}\n`)
    console.log(`Feature boundary budget updated: ${Object.values(current).reduce((a, b) => a + b, 0)} violations`)
    return
  }
  const budget = JSON.parse(fs.readFileSync(BUDGET, 'utf8')).violations
  if (!budget) throw new Error('Feature boundary budget must contain violations; review and update it')
  const failures = budgetDifferences(current, budget)
  if (failures.length) {
    console.error('Feature boundary baseline differs from actual imports:')
    for (const failure of failures) console.error(`  ${failure}`)
    console.error('Remove new violations; after removing existing violations, review and update the baseline.')
    process.exitCode = 1
    return
  }
  console.log(`Feature boundaries OK: ${Object.values(current).reduce((a, b) => a + b, 0)} existing violations within budget`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main()
