import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const source = fileURLToPath(new URL('../src/', import.meta.url))
// Keep this registry aligned with docs/studio/STRUCTURE.md.
const tokenFiles = new Set([
  'index.css',
  'app/styles/workbench.css',
  'app/styles/buttons.css',
  'shared/styles/foundation-tokens.css',
  'shared/styles/surface-tokens.css',
  'shared/styles/editor-tokens.css',
  'shared/styles/chart-tokens.css',
  'shared/styles/legacy-tokens.css',
  'shared/styles/github-dark-tokens.css',
  'shared/styles/github-dark-foundation.css',
])

// These values intentionally live outside CSS: Ant Design runs color algorithms;
// the standalone report and brand artwork retain their fixed presentation.
const fixedColorFiles = new Set([
  'app/providers/ThemeProvider.tsx',
  'features/api-automation/utils/collectionRunReport.ts',
  'shared/components/MtxLogo/MtxLogo.tsx',
])

const namedColors = new Set(`aliceblue antiquewhite aqua aquamarine azure beige bisque
black blanchedalmond blue blueviolet brown burlywood cadetblue chartreuse chocolate
coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray
darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred
darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise
darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite
forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray green greenyellow grey
honeydew hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen
lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen
lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey
lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine
mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen
mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite
navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen
paleturquoise palevioletred papayawhip peachpuff peru pink plum powderblue purple
rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell
sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan
teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen`.split(/\s+/))

// Mask comments and quoted content without changing offsets/line numbers. Hex-looking
// selectors and strings (including SVG data URLs) must not be mistaken for colors.
function maskNonCode(css) {
  return css.replace(/\/\*[\s\S]*?\*\/|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'/g,
    text => text.replace(/[^\n]/g, ' '))
}

function literalColors(value) {
  // var() identifiers may contain color words; only their fallback is a color value.
  const withoutVariableNames = value.replace(/--[\w-]+/g, '')
  const functionsOrHex = withoutVariableNames.match(/#[\da-f]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\s*\(/gi) ?? []
  const names = (withoutVariableNames.match(/\b[a-z][\w-]*\b/gi) ?? [])
    .filter(word => namedColors.has(word.toLowerCase()))
  return [...functionsOrHex, ...names]
}

async function* sourceFiles(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) yield* sourceFiles(path)
    else if (entry.isFile() && /\.(css|tsx?)$/.test(entry.name)) yield path
  }
}

const violations = []
let checked = 0
let checkedCode = 0
for await (const file of sourceFiles(source)) {
  const path = relative(source, file).replaceAll('\\', '/')
  const text = await readFile(file, 'utf8')
  if (!path.endsWith('.css')) {
    if (fixedColorFiles.has(path) || /\.(test|spec)\.tsx?$/.test(path) || /(?:^|\/)(?:test|__fixtures__)\//.test(path)) continue
    checkedCode += 1
    const ast = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true)
    const visit = node => {
      // AST traversal excludes comments and regex literals. Ant Design named
      // statuses ("gold", "success", etc.) are semantic API inputs, so only
      // explicit hex/function colors are rejected in JavaScript strings.
      if (ts.isStringLiteralLike(node) || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
        const colors = node.text.match(/#[\da-f]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\s*\(/gi)
        if (colors) {
          const { line } = ast.getLineAndCharacterOfPosition(node.getStart(ast))
          violations.push(`${path}:${line + 1} string: ${colors.join(', ')}`)
        }
      }
      ts.forEachChild(node, visit)
    }
    visit(ast)
    continue
  }
  checked += 1
  const css = maskNonCode(text)
  // Match declarations, including multiple declarations on one line and nested rules.
  // The lookahead leaves each separator available for the next declaration.
  for (const match of css.matchAll(/(?:^|[;{}])\s*([\w-]+)\s*:\s*([^;{}]+)(?=;|})/g)) {
    const [, property, value] = match
    if (tokenFiles.has(path) && property.startsWith('--')) continue
    const colors = literalColors(value)
    if (colors.length === 0) continue
    const declarationStart = match.index + match[0].indexOf(property)
    const line = css.slice(0, declarationStart).split('\n').length
    violations.push(`${path}:${line} ${property}: ${colors.join(', ')}`)
  }
}

if (violations.length > 0) {
  console.error('Literal colors must live in registered CSS tokens or fixed-color modules:')
  console.error(violations.join('\n'))
  process.exitCode = 1
} else {
  console.log(`Theme color check passed (${checked} CSS files, ${checkedCode} TS/TSX files; registered color sources only).`)
}
