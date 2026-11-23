import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const DIST = join(ROOT, 'dist')
const INITIAL_JS_GZIP_BUDGET_KB = 260
const INITIAL_CSS_GZIP_BUDGET_KB = 60
const ROUTE_BUDGETS = {
  login: { entries: ['index.html', 'src/features/auth/pages/AuthPage.tsx'], js: 280, css: 50 },
  projects: { entries: ['index.html', 'src/app/layouts/AppShell.tsx', 'src/features/projects/pages/ProjectsPage.tsx'], js: 530, css: 55 },
  requirementDetail: { entries: ['index.html', 'src/app/pages/RequirementDetailPage.tsx'], js: 1030, css: 65 },
  testOrderWorkspace: { entries: ['index.html', 'src/features/test-orders/pages/TestOrderWorkspacePage.tsx'], js: 660, css: 55 },
  uiSuiteCase: { entries: ['index.html', 'src/features/ui-automation/pages/UiTestSuiteCasePage.tsx'], js: 715, css: 55 },
  apiCollectionDetail: { entries: ['index.html', 'src/features/api-automation/pages/ApiCollectionDetailPage.tsx'], js: 585, css: 50 },
  bugDetail: { entries: ['index.html', 'src/features/bugs/pages/BugDetailPage.tsx'], js: 605, css: 50 },
  perfRunDetail: { entries: ['index.html', 'src/features/performance/pages/PerformanceRunDetailPage.tsx'], js: 425, css: 45 },
}

const html = await readFile(join(DIST, 'index.html'), 'utf8')
const initialAssets = [...new Set(
  [...html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)].map(match => match[1]),
)]
if (initialAssets.length === 0) {
  console.error('Bundle budget check failed: dist/index.html references no JS or CSS assets')
  process.exit(1)
}

async function sizeInKb(asset) {
  const file = join(DIST, asset.replace(/^\//, ''))
  return gzipSync(await readFile(file)).byteLength / 1024
}

const measured = []
for (const asset of initialAssets) {
  measured.push({ asset, kb: await sizeInKb(asset) })
}
const js = measured.filter(item => item.asset.endsWith('.js'))
const css = measured.filter(item => item.asset.endsWith('.css'))
const sum = items => items.reduce((total, item) => total + item.kb, 0)
const jsKb = sum(js)
const cssKb = sum(css)
const allJs = (await readdir(join(DIST, 'assets'))).filter(name => name.endsWith('.js')).length
const nonInitialChunks = Math.max(0, allJs - js.length)

const failed = []
if (jsKb > INITIAL_JS_GZIP_BUDGET_KB) failed.push(`initial JS ${jsKb.toFixed(1)} kB > ${INITIAL_JS_GZIP_BUDGET_KB} kB`)
if (cssKb > INITIAL_CSS_GZIP_BUDGET_KB) failed.push(`initial CSS ${cssKb.toFixed(1)} kB > ${INITIAL_CSS_GZIP_BUDGET_KB} kB`)

// Include each route's lazy entry and its static dependency graph. Other lazy
// entries remain excluded because they are not necessarily requested on load.
const manifest = JSON.parse(await readFile(join(DIST, '.vite', 'manifest.json'), 'utf8'))
for (const [route, budget] of Object.entries(ROUTE_BUDGETS)) {
  const visited = new Set()
  const files = new Set()
  function visit(key) {
    if (visited.has(key)) return
    const chunk = manifest[key]
    if (!chunk) throw new Error(`Missing route manifest entry: ${key}`)
    visited.add(key)
    files.add(chunk.file)
    for (const cssFile of chunk.css ?? []) files.add(cssFile)
    for (const dependency of chunk.imports ?? []) visit(dependency)
  }
  budget.entries.forEach(visit)
  const assets = await Promise.all([...files].map(async asset => ({ asset, kb: await sizeInKb(asset) })))
  const routeJs = sum(assets.filter(item => item.asset.endsWith('.js')))
  const routeCss = sum(assets.filter(item => item.asset.endsWith('.css')))
  console.log(`Route ${route}: JS ${routeJs.toFixed(1)} / ${budget.js} kB gzip; CSS ${routeCss.toFixed(1)} / ${budget.css} kB gzip`)
  if (routeJs > budget.js) failed.push(`${route} JS ${routeJs.toFixed(1)} kB > ${budget.js} kB`)
  if (routeCss > budget.css) failed.push(`${route} CSS ${routeCss.toFixed(1)} kB > ${budget.css} kB`)
}

console.log(
  `Initial bundle: JS ${jsKb.toFixed(1)} kB gzip / ${INITIAL_JS_GZIP_BUDGET_KB} kB budget; ` +
  `CSS ${cssKb.toFixed(1)} kB gzip / ${INITIAL_CSS_GZIP_BUDGET_KB} kB budget; ${nonInitialChunks} non-initial JS chunks.`,
)
for (const item of measured.sort((left, right) => right.kb - left.kb)) {
  console.log(`  ${item.kb.toFixed(1).padStart(7)} kB  ${item.asset}`)
}

if (failed.length > 0) {
  console.error('Bundle budget check failed:\n' + failed.map(item => `  - ${item}`).join('\n'))
  console.error('Reduce the initial route graph or consciously ratchet scripts/check-bundle-budget.mjs.')
  process.exit(1)
}
