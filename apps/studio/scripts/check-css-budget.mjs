import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../src/', import.meta.url))
const baselinePath = fileURLToPath(new URL('./css-budget.json', import.meta.url))
const update = process.argv.includes('--update')

const THIRD_PARTY_VAR = /^--(?:ant|rc|cm|codemirror|recharts|react-flow|mermaid|hljs)-/

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

// Replace comments with spaces while preserving offsets and line numbers.
function maskComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/.*$/gm, (m, prefix) => prefix + ' '.repeat(m.length - prefix.length))
}

function collectCustomProperties(files) {
  const definitions = new Set()
  const uses = new Map()
  const define = name => definitions.add(name)
  const use = (name, file, hasFallback) => {
    if (!uses.has(name)) uses.set(name, { files: new Set(), hasFallback: false })
    const entry = uses.get(name)
    entry.files.add(file)
    entry.hasFallback ||= hasFallback
  }

  const addDefinitions = (text, pattern) => {
    for (const match of text.matchAll(pattern)) define(match[1])
  }

  for (const [file, text] of files) {
    addDefinitions(text, /^\s*(--[A-Za-z0-9_-]+)\s*:/gm)
    addDefinitions(text, /['"](--[A-Za-z0-9_-]+)['"]\s*:/g)
    addDefinitions(text, /setProperty\(\s*['"](--[A-Za-z0-9_-]+)['"]/g)

    let index = 0
    while ((index = text.indexOf('var(', index)) !== -1) {
      let depth = 0
      let end = index + 4
      let comma = false
      for (; end < text.length; end += 1) {
        const ch = text[end]
        if (ch === '(') depth += 1
        else if (ch === ')') {
          if (depth === 0) break
          depth -= 1
        } else if (ch === ',' && depth === 0) comma = true
      }
      if (end >= text.length) break
      const args = text.slice(index + 4, end).trim()
      const name = args.match(/^(--[A-Za-z0-9_-]+)/)?.[1]
      if (name) use(name, file, comma)
      index = end + 1
    }
  }
  return { definitions, uses }
}

function countByFile(files, pattern) {
  const counts = {}
  for (const [file, text] of files) {
    const count = (text.match(pattern) ?? []).length
    if (count > 0) counts[file] = count
  }
  return counts
}

const absolute = await walk(root)
const cssFiles = []
const sourceFiles = []
for (const path of absolute) {
  const rel = relative(root, path).replaceAll('\\', '/')
  if (path.endsWith('.css')) {
    const text = maskComments(await readFile(path, 'utf8'))
    cssFiles.push([`src/${rel}`, text])
  } else if (/\.(ts|tsx|html)$/.test(path)) {
    sourceFiles.push([`src/${rel}`, maskComments(await readFile(path, 'utf8'))])
  }
}

const importantByFile = countByFile(cssFiles, /!important/g)
const longPrefixByFile = countByFile(cssFiles, /\.app-shell\.app-shell-macos/g)
const important = Object.values(importantByFile).reduce((sum, n) => sum + n, 0)
const longPrefix = Object.values(longPrefixByFile).reduce((sum, n) => sum + n, 0)

const { definitions, uses } = collectCustomProperties([...cssFiles, ...sourceFiles])
const undefinedVars = []
const fallbackUndefinedVars = []
for (const [name, entry] of uses) {
  if (definitions.has(name) || THIRD_PARTY_VAR.test(name) || name.endsWith('-')) continue
  if (entry.hasFallback) fallbackUndefinedVars.push(name)
  else undefinedVars.push(name)
}
undefinedVars.sort()
fallbackUndefinedVars.sort()

const current = {
  important,
  importantByFile,
  longPrefix,
  longPrefixByFile,
  undefinedWithoutFallback: undefinedVars,
  fallbackUndefinedVars,
}

if (update) {
  await writeFile(baselinePath, `${JSON.stringify(current, null, 2)}\n`)
  console.log(`CSS budget baseline updated: ${important} !important, ${longPrefix} long prefixes, ${undefinedVars.length} undefined, ${fallbackUndefinedVars.length} fallback-backed.`)
  process.exit(0)
}

const baseline = JSON.parse(await readFile(baselinePath, 'utf8'))
const errors = []

if (important > baseline.important) {
  errors.push(`!important 总数增加：${baseline.important} -> ${important}`)
}
for (const [file, count] of Object.entries(importantByFile)) {
  const allowed = baseline.importantByFile[file] ?? 0
  if (count > allowed) errors.push(`${file}: !important ${allowed} -> ${count}`)
}

if (longPrefix > baseline.longPrefix) {
  errors.push(`长前缀总数增加：${baseline.longPrefix} -> ${longPrefix}`)
}
for (const [file, count] of Object.entries(longPrefixByFile)) {
  const allowed = baseline.longPrefixByFile[file] ?? 0
  if (count > allowed) errors.push(`${file}: 长前缀 ${allowed} -> ${count}`)
}

const allowedUndefined = new Set(baseline.undefinedWithoutFallback ?? [])
for (const name of undefinedVars) {
  if (!allowedUndefined.has(name)) errors.push(`未定义且无回退的 CSS 变量：${name}`)
}
const allowedFallback = new Set(baseline.fallbackUndefinedVars ?? [])
for (const name of fallbackUndefinedVars) {
  if (!allowedFallback.has(name)) errors.push(`未定义但有回退的 CSS 变量：${name}`)
}

if (errors.length) {
  console.error('CSS budget check failed:\n' + errors.map(e => `  - ${e}`).join('\n'))
  console.error('\n如为有意增加，请运行 `node scripts/check-css-budget.mjs --update` 更新基线，并在评审中说明。')
  process.exit(1)
}

console.log(`CSS budget OK: ${important} !important, ${longPrefix} long prefixes, ${undefinedVars.length} undefined, ${fallbackUndefinedVars.length} fallback-backed.`)
