import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const DIST = join(ROOT, 'dist')
const INITIAL_JS_GZIP_BUDGET_KB = 260
const INITIAL_CSS_GZIP_BUDGET_KB = 60

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
