#!/usr/bin/env node
/**
 * Tailwind className 门禁：约束 TSX 中新增 `!` 修饰符与重复 utility 串。
 *
 * 用法：
 *   node scripts/check-tailwind-classes.mjs            # 检查
 *   node scripts/check-tailwind-classes.mjs --update   # 更新重复串基线
 *
 * ADR 0004 禁止用 Tailwind 的 `!` 绕过级联，也禁止在多个页面复制同一串 utility。
 * 重复串按「静态 className 串 + 至少 2 个文件 + 至少 3 次」统计；`!` 零容忍。
 */
import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const root = fileURLToPath(new URL('../', import.meta.url))
const srcRoot = join(root, 'src')
const baselinePath = join(root, 'scripts', 'tailwind-class-budget.json')
const update = process.argv.includes('--update')
const DUPLICATE_THRESHOLD = 3
const DUPLICATE_MIN_FILES = 2

// 只把明确的 utility 特征算作候选，避免把纯 legacy 类名误报为重复 utility。
const UTILITY_TOKEN = /(?:^|:)(?:flex|grid|block|inline|hidden|relative|absolute|fixed|sticky|items-|justify-|gap-|p[trblxy]?-|m[trblxy]?-|w-|h-|min-|max-|text-|bg-|border|rounded|shadow|overflow|font-|leading-|tracking-|opacity-|z-|top-|left-|right-|bottom-|col-|row-|space-|cursor-|transition|duration-|ease-|hover:|focus|active:|disabled:|max-|min-|sm:|md:|lg:|xl:|\[&)/

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__fixtures__' || entry.name === 'node_modules') continue
      yield* walk(path)
    } else if (/\.tsx?$/.test(entry.name) && !/\.(test|spec)\.tsx?$/.test(entry.name)) {
      yield path
    }
  }
}

function sourceFiles() {
  return walk(srcRoot)
}

function isClassNameAttribute(node) {
  return ts.isJsxAttribute(node)
    && ts.isIdentifier(node.name)
    && node.name.text === 'className'
    && Boolean(node.initializer)
}

function collectStrings(expression, add) {
  if (!expression) return
  if (ts.isStringLiteralLike(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
    add(expression.text, false, expression)
    return
  }
  if (ts.isTemplateExpression(expression)) {
    // 插值模板无法作为稳定的重复串比较；静态片段仍参与 `!` 检查。
    if (expression.head.text) add(expression.head.text, true, expression.head)
    for (const span of expression.templateSpans) {
      if (span.literal.text) add(span.literal.text, true, span.literal)
    }
    return
  }
  if (ts.isFunctionLike(expression)) return
  ts.forEachChild(expression, child => collectStrings(child, add))
}

const classStrings = []
for await (const file of sourceFiles()) {
  const text = await readFile(file, 'utf8')
  const sourceFile = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const visit = node => {
    if (isClassNameAttribute(node)) {
      const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1
      const add = (value, dynamic, nodeForLine) => {
        classStrings.push({
          file: relative(root, file).split('\\').join('/'),
          line: nodeForLine
            ? sourceFile.getLineAndCharacterOfPosition(nodeForLine.getStart(sourceFile)).line + 1
            : line,
          value,
          dynamic,
        })
      }
      if (ts.isStringLiteral(node.initializer)) add(node.initializer.text, false, node.initializer)
      else if (ts.isJsxExpression(node.initializer)) collectStrings(node.initializer.expression, add)
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile)
}

const important = []
const groups = new Map()
for (const item of classStrings) {
  const normalized = item.value.replace(/\s+/g, ' ').trim()
  if (!normalized) continue
  const tokens = normalized.split(' ').filter(Boolean)
  for (const token of tokens) {
    if (token.startsWith('!') || token.endsWith('!')) {
      important.push(`${item.file}:${item.line} ${token}`)
    }
  }
  // 动态片段不是完整 className，无法判断重复；只检查 `!`。
  if (item.dynamic || tokens.length < 2) continue
  if (!tokens.some(token => UTILITY_TOKEN.test(token))) continue
  const entry = groups.get(normalized) ?? { files: new Set(), count: 0, locations: [] }
  entry.count += 1
  entry.files.add(item.file)
  if (entry.locations.length < 5) entry.locations.push(`${item.file}:${item.line}`)
  groups.set(normalized, entry)
}

const duplicates = [...groups.entries()]
  .filter(([, entry]) => entry.count >= DUPLICATE_THRESHOLD && entry.files.size >= DUPLICATE_MIN_FILES)
  .map(([className, entry]) => ({ className, count: entry.count, files: entry.files.size, locations: entry.locations }))
  .sort((a, b) => b.count - a.count || a.className.localeCompare(b.className))

const current = duplicateEntriesToBudget(duplicates)
if (update) {
  await writeFile(baselinePath, `${JSON.stringify(current, null, 2)}\n`)
  console.log(`Tailwind class budget updated: ${duplicates.length} duplicate className groups`)
  process.exit(0)
}

let baseline
try {
  baseline = JSON.parse(await readFile(baselinePath, 'utf8'))
} catch {
  console.error(`缺少 ${relative(root, baselinePath)}；先运行 node scripts/check-tailwind-classes.mjs --update 并评审基线`)
  process.exit(1)
}
const allowed = new Map((baseline.duplicates ?? []).map(entry => [entry.className, entry.count]))

const failures = []
if (important.length > 0) {
  failures.push('禁止在 Tailwind className 中使用 `!` 修饰符（ADR 0004）：')
  failures.push(...important.map(entry => `  - ${entry}`))
}
for (const duplicate of duplicates) {
  const limit = allowed.get(duplicate.className) ?? 0
  if (duplicate.count > limit) {
    failures.push(`重复 className 串${limit === 0 ? '新增' : '增加'}（${duplicate.count} 次 / ${duplicate.files} 个文件，基线 ${limit}）：`)
    failures.push(`  - "${duplicate.className}"`)
    failures.push(...duplicate.locations.map(location => `    ${location}`))
  }
}

if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}
console.log(`Tailwind class check passed (${classStrings.length} className strings, ${duplicates.length} duplicate groups within baseline, no ! modifiers)`)

function duplicateEntriesToBudget(entries) {
  return {
    version: 1,
    threshold: DUPLICATE_THRESHOLD,
    minFiles: DUPLICATE_MIN_FILES,
    duplicates: entries.map(entry => ({ className: entry.className, count: entry.count })),
  }
}
