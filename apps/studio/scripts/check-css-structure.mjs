#!/usr/bin/env node
/**
 * CSS 结构门禁：约束新增全局样式、跨 feature 导入、文件体量（单文件 ≤600 行）、重复规则体与 App.css 回归。
 *
 * 用法：
 *   node scripts/check-css-structure.mjs            # 检查
 *   node scripts/check-css-structure.mjs --init     # 首次生成 baseline
 *   node scripts/check-css-structure.mjs --update   # 收紧计数/重复体，不自动放行新增全局文件
 *
 * baseline 中的 allowedGlobalCss、crossFeatureCssImports、sharedModuleViolations
 * 只能手工增删；--update 只更新可自动测量的计数与重复体，避免把新债务静默写进基线。
 */
import { createHash } from 'node:crypto'
import { readdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const srcRoot = join(root, 'src')
const baselinePath = join(root, 'scripts', 'css-structure-budget.json')
const init = process.argv.includes('--init')
const update = process.argv.includes('--update')

// json-editor-* / api-case-run-result-* / api-collection-run-* / base-services-* 是 shared 组件或跨 feature 视图的兼容类族。
// success/failed/error/skipped/expanded/compact 是这些视图共用的状态修饰类。
const THIRD_PARTY_CLASS = /^(?:ant-|anticon|cm-|react-flow|recharts|hljs|mermaid|json-editor-|api-case-run-result-|api-collection-|base-services-|sprint-card-|success|failed|error|skipped|expanded|compact)/
const SUBSTANTIVE_BODY = /\S/

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...await walk(path))
    else files.push(path)
  }
  return files
}

function posix(path) {
  return path.split(sep).join('/')
}

function rel(path) {
  return posix(relative(root, path))
}

function maskComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/.*$/gm, (m, prefix) => prefix + ' '.repeat(m.length - prefix.length))
}

function splitBalanced(value, separator) {
  const parts = []
  let depth = 0
  let start = 0
  for (let index = 0; index < value.length; index += 1) {
    const ch = value[index]
    if (ch === '(' || ch === '[') depth += 1
    else if (ch === ')' || ch === ']') depth = Math.max(0, depth - 1)
    else if (ch === separator && depth === 0) {
      parts.push(value.slice(start, index).trim())
      start = index + 1
    }
  }
  parts.push(value.slice(start).trim())
  return parts.filter(Boolean)
}

function parseRules(text) {
  const masked = maskComments(text)
  const rules = []
  for (const match of masked.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const prelude = match[1].trim()
    if (!prelude || prelude.startsWith('@')) continue
    if (/^(?:from|to|\d+(?:\.\d+)?%)$/.test(prelude)) continue
    const declarations = splitBalanced(match[2], ';')
      .filter(item => item.includes(':'))
      .map(item => item.replace(/\s+/g, ' ').trim())
    if (!declarations.length || !SUBSTANTIVE_BODY.test(match[2])) continue
    rules.push({
      selectors: splitBalanced(prelude, ','),
      declarations,
    })
  }
  return rules
}

function normalizedBody(declarations) {
  return declarations.join(';')
}

function duplicateBodies(rules) {
  const groups = new Map()
  for (const rule of rules) {
    if (rule.declarations.length < 3) continue
    const body = normalizedBody(rule.declarations)
    if (body.length < 40) continue
    const hash = createHash('sha256').update(body).digest('hex').slice(0, 16)
    const entry = groups.get(hash) ?? { count: 0, sample: body.slice(0, 180) }
    entry.count += 1
    groups.set(hash, entry)
  }
  return groups
}

function cssImportSpecs(text) {
  const specs = []
  for (const match of text.matchAll(/@import\s+(?:url\()?['"]([^'"]+\.css)['"]/g)) {
    specs.push(match[1])
  }
  return specs
}

function tsImportSpecs(text) {
  const specs = []
  for (const match of text.matchAll(/(?:from\s+|import\s+)['"]([^'"]+\.css)['"]/g)) {
    specs.push(match[1])
  }
  return specs
}

function resolveSpec(importer, spec) {
  if (!spec || /^[a-z]+:/i.test(spec)) return null
  if (spec.startsWith('@/')) return posix(join(srcRoot, spec.slice(2)))
  if (spec.startsWith('.')) return resolve(dirname(importer), spec)
  return null
}

function featureOf(path) {
  const parts = rel(path).split('/')
  const index = parts.indexOf('features')
  return index >= 0 ? parts[index + 1] : null
}

function isSharedModule(path) {
  return rel(path).startsWith('src/shared/') && path.endsWith('.module.css')
}

function sharedModuleViolations(path, text) {
  if (!isSharedModule(path)) return []
  const violations = []
  for (const match of maskComments(text).matchAll(/:global\(([^)]*)\)/g)) {
    const selector = match[1]
    for (const token of selector.matchAll(/\.([a-zA-Z_][\w-]*)/g)) {
      if (THIRD_PARTY_CLASS.test(token[1])) continue
      violations.push(`${rel(path)}: ${match[0]}`)
      break
    }
  }
  return [...new Set(violations)]
}

const files = await walk(srcRoot)
const cssFiles = files.filter(file => file.endsWith('.css'))
const sourceFiles = files.filter(file => /\.(ts|tsx)$/.test(file))

const cssText = new Map()
for (const file of cssFiles) cssText.set(file, await readFile(file, 'utf8'))
const sourceText = new Map()
for (const file of sourceFiles) sourceText.set(file, await readFile(file, 'utf8'))

const importers = new Map()
const crossFeatureImports = []
for (const file of [...cssFiles, ...sourceFiles]) {
  const text = cssText.get(file) ?? sourceText.get(file) ?? ''
  const specs = file.endsWith('.css') ? cssImportSpecs(text) : tsImportSpecs(text)
  for (const spec of specs) {
    const target = resolveSpec(file, spec)
    if (!target) continue
    const entry = importers.get(target) ?? new Set()
    entry.add(file)
    importers.set(target, entry)
    const fromFeature = featureOf(file)
    const toFeature = featureOf(target)
    if (fromFeature && toFeature && fromFeature !== toFeature) {
      crossFeatureImports.push(`${rel(file)} -> ${rel(target)}`)
    }
  }
}
const uniqueCrossFeature = [...new Set(crossFeatureImports)].sort()

const counts = {}
const duplicates = new Map()
for (const file of cssFiles) {
  const rules = parseRules(cssText.get(file))
  counts[rel(file)] = {
    rules: rules.length,
    declarations: rules.reduce((sum, rule) => sum + rule.declarations.length, 0),
    selectors: rules.reduce((sum, rule) => sum + rule.selectors.length, 0),
  }
  for (const [hash, entry] of duplicateBodies(rules)) {
    const existing = duplicates.get(hash) ?? { count: 0, sample: entry.sample }
    existing.count += entry.count
    duplicates.set(hash, existing)
  }
}
const duplicateBaseline = Object.fromEntries(
  [...duplicates.entries()].filter(([, entry]) => entry.count > 1).sort(([a], [b]) => a.localeCompare(b)),
)

const orphanCss = cssFiles
  .filter(file => !importers.has(file))
  .map(rel)
  .sort()

const sharedViolations = cssFiles.flatMap(file => sharedModuleViolations(file, cssText.get(file))).sort()

const globalCss = cssFiles
  .filter(file => !file.endsWith('.module.css'))
  .map(rel)
  .sort()

const tailwind = cssText.get(join(srcRoot, 'shared', 'styles', 'tailwind.css')) ?? ''
const layerOk = /@layer\s+theme,\s*base,\s*antd,\s*components,\s*utilities;/.test(tailwind)
  && /@import\s+["']tailwindcss\/utilities\.css["']\s+layer\(utilities\)/.test(tailwind)

const current = {
  version: 1,
  allowedGlobalCss: globalCss,
  crossFeatureCssImports: uniqueCrossFeature,
  orphanCss,
  sharedModuleViolations: sharedViolations,
  files: counts,
  duplicateBodies: duplicateBaseline,
}

if (init) {
  await writeFile(baselinePath, `${JSON.stringify(current, null, 2)}\n`)
  console.log(`CSS structure baseline initialized: ${globalCss.length} global CSS, ${uniqueCrossFeature.length} cross-feature imports, ${Object.keys(duplicateBaseline).length} duplicate body groups.`)
  process.exit(0)
}

let baseline
try {
  baseline = JSON.parse(await readFile(baselinePath, 'utf8'))
} catch {
  console.error(`缺少 ${rel(baselinePath)}，请先运行 node scripts/check-css-structure.mjs --init`)
  process.exit(1)
}

const errors = []
if (!layerOk) {
  errors.push('shared/styles/tailwind.css 缺少 layer 声明或 utilities 层级导入')
}
const MAX_CSS_LINES = 600
for (const file of cssFiles) {
  const lines = (cssText.get(file).match(/\n/g) ?? []).length
  if (lines > MAX_CSS_LINES) errors.push(`${rel(file)}: ${lines} 行，超过单文件 ${MAX_CSS_LINES} 行上限`)
}
if (cssFiles.some(file => rel(file) === 'src/App.css')) {
  errors.push('src/App.css 已删除；全局层导入直接写在 src/app/styles/theme.css')
}
if (!init && !update) {
  const allowedGlobal = new Set(baseline.allowedGlobalCss ?? [])
  for (const file of globalCss) {
    if (!allowedGlobal.has(file)) errors.push(`新增全局/feature CSS：${file}（需手工加入 allowedGlobalCss 并评审）`)
  }
  const allowedCross = new Set(baseline.crossFeatureCssImports ?? [])
  for (const entry of uniqueCrossFeature) {
    if (!allowedCross.has(entry)) errors.push(`新增跨 feature CSS 导入：${entry}`)
  }
  const allowedShared = new Set(baseline.sharedModuleViolations ?? [])
  for (const entry of sharedViolations) {
    if (!allowedShared.has(entry)) errors.push(`shared Module 新增 feature 私有选择器：${entry}`)
  }
  const allowedOrphans = new Set(baseline.orphanCss ?? [])
  for (const file of orphanCss) {
    if (!allowedOrphans.has(file)) errors.push(`新增无 importer 的 CSS：${file}`)
  }
}

for (const [file, count] of Object.entries(counts)) {
  const allowed = baseline.files?.[file]
  if (!allowed) continue
  for (const key of ['rules', 'declarations', 'selectors']) {
    if (count[key] > allowed[key]) {
      errors.push(`${file}: ${key} ${allowed[key]} -> ${count[key]}`)
    }
  }
}

for (const [hash, entry] of Object.entries(duplicateBaseline)) {
  const allowed = baseline.duplicateBodies?.[hash]?.count ?? 0
  if (entry.count > allowed) {
    errors.push(`重复规则体增加：${entry.count} 次（${entry.sample.slice(0, 80)}…）`)
  }
}

if (update) {
  const next = {
    ...current,
    allowedGlobalCss: (baseline.allowedGlobalCss ?? []).filter(file => globalCss.includes(file)),
    crossFeatureCssImports: (baseline.crossFeatureCssImports ?? []).filter(entry => uniqueCrossFeature.includes(entry)),
    sharedModuleViolations: (baseline.sharedModuleViolations ?? []).filter(entry => sharedViolations.includes(entry)),
    orphanCss: (baseline.orphanCss ?? []).filter(entry => orphanCss.includes(entry)),
  }
  await writeFile(baselinePath, `${JSON.stringify(next, null, 2)}\n`)
  const addedGlobals = globalCss.filter(file => !(baseline.allowedGlobalCss ?? []).includes(file))
  if (addedGlobals.length) {
    console.warn(`注意：以下新全局 CSS 未写入 allowlist，需手工评审：\n  ${addedGlobals.join('\n  ')}`)
  }
  console.log(`CSS structure baseline updated: ${Object.keys(counts).length} files, ${Object.keys(duplicateBaseline).length} duplicate body groups.`)
  process.exit(0)
}

if (errors.length) {
  console.error('CSS structure check failed:\n' + errors.map(error => `  - ${error}`).join('\n'))
  process.exit(1)
}

console.log(`CSS structure OK: ${cssFiles.length} CSS files, ${globalCss.length} global, ${uniqueCrossFeature.length} cross-feature imports, ${Object.keys(duplicateBaseline).length} duplicate body groups.`)
