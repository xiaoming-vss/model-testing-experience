/**
 * jsdom 不解析 CSS cascade layers；测试注入原始 CSS 前先去掉指定 layer 的外层块，
 * 让分层后的共享规则仍能参与 computed style 断言。
 */
export function unwrapCssLayer(css: string, layer: string): string {
  const opener = new RegExp(`@layer\\s+${layer}\\s*\\{`, 'g')
  let result = ''
  let cursor = 0
  let match: RegExpExecArray | null

  while ((match = opener.exec(css))) {
    result += css.slice(cursor, match.index)

    let depth = 1
    let index = opener.lastIndex
    while (index < css.length && depth > 0) {
      if (css[index] === '{') depth += 1
      else if (css[index] === '}') depth -= 1
      index += 1
    }

    result += css.slice(opener.lastIndex, index - 1)
    cursor = index
    opener.lastIndex = index
  }

  return result + css.slice(cursor)
}
