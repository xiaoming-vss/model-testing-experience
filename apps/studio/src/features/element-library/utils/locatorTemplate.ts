import type { ElementLocatorType } from '../types'

export function parameterNames(template: string) {
  return [...new Set(Array.from(template.matchAll(/\{\{(.*?)\}\}/g), match => match[1].split('|')[0].trim()).filter(Boolean))]
}

function xpathLiteral(value: string) {
  if (!value.includes("'")) return "'" + value + "'"
  if (!value.includes('"')) return '"' + value + '"'
  return 'concat(' + value.split("'").map(part => "'" + part + "'").join(", \"'\", ") + ')'
}

function cssSample(value: string, template: string, offset: number) {
  let quote = ''
  for (let i = 0; i < offset; i += 1) {
    const character = template[i]
    if (character === '\\') i += 1
    else if (character === quote) quote = ''
    else if (!quote && (character === '"' || character === "'")) quote = character
  }
  if (quote) {
    return value.replaceAll('\\', '\\\\').replaceAll(quote, '\\' + quote)
      .replace(/[\n\r\f]/g, character => '\\' + character.charCodeAt(0).toString(16) + ' ')
  }
  const identifierContinues = /[\w\u0080-\uFFFF\\-]/u.test(template.slice(offset - 1, offset))
  return identifierContinues ? CSS.escape('_' + value).slice(1) : CSS.escape(value)
}

export function renderLocatorSample(template: string, type: ElementLocatorType, values: ReadonlyMap<string, string>) {
  return template.replace(/\{\{(.*?)\}\}/g, (_, expression: string, offset: number) => {
    const value = values.get(expression.split('|')[0].trim()) ?? ''
    if (type === 'xpath') return xpathLiteral(value)
    if (type === 'css') return cssSample(value, template, offset)
    return value
  })
}
