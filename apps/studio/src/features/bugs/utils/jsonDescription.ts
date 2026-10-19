/** Format validated JSON lexically so large numbers and duplicate keys stay intact. */
function formatJson(source: string): string {
  let output = '', depth = 0, quoted = false, escaped = false
  const newline = () => { output = output.trimEnd() + '\n' + '  '.repeat(depth) }
  for (const char of source) {
    if (quoted) {
      output += char
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') quoted = false
      continue
    }
    if (/\s/.test(char)) continue
    if (char === '"') { quoted = true; output += char }
    else if (char === '{' || char === '[') { output += char; depth++; newline() }
    else if (char === '}' || char === ']') { depth--; newline(); output += char }
    else if (char === ',') { output += char; newline() }
    else if (char === ':') output += ': '
    else output += char
  }
  return output
}

/** Only complete object/array JSON in plain sibling paragraphs is promoted. No stored HTML is changed. */
export function recognizeJsonDescription(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  let changed = false
  // Existing code, lists, tables and formatted/media paragraphs retain their original structure.
  for (const parent of [doc.body, ...doc.body.querySelectorAll('div')]) {
    if (parent.closest('pre, code, table, li, blockquote')) continue
    const nodes = Array.from(parent.childNodes)
    for (let start = 0; start < nodes.length; start++) {
      const first = nodes[start]
      const plain = (node: Node) => node.nodeType === Node.TEXT_NODE
        || (node instanceof Element && node.tagName === 'P' && !node.querySelector(':not(br)') && !node.hasAttribute('data-file-id'))
      const content = (node: Node) => {
        const clone = node.cloneNode(true)
        if (clone instanceof Element) clone.querySelectorAll('br').forEach(br => br.replaceWith('\n'))
        return clone.textContent ?? ''
      }
      if (!plain(first) || !/^\s*[[{]/.test(content(first))) continue
      let source = '', depth = 0, quoted = false, escaped = false, end = start
      let complete = false
      for (; end < nodes.length; end++) {
        if (!plain(nodes[end])) break
        const part = content(nodes[end])
        source += (source ? '\n' : '') + part
        for (const char of part) {
          if (quoted) {
            if (escaped) escaped = false
            else if (char === '\\') escaped = true
            else if (char === '"') quoted = false
          } else if (char === '"') quoted = true
          else if (char === '{' || char === '[') depth++
          else if (char === '}' || char === ']') depth--
        }
        if (depth <= 0 && !quoted) { complete = true; break }
        if (source.length > 200_000) break
      }
      if (complete) {
        try {
          const parsed: unknown = JSON.parse(source)
          if (parsed && typeof parsed === 'object') {
            const pre = doc.createElement('pre'), code = doc.createElement('code')
            code.className = 'language-json'
            code.textContent = formatJson(source)
            pre.append(code)
            first.before(pre)
            for (let i = start; i <= end; i++) nodes[i].remove()
            changed = true
          }
        } catch { /* Invalid or mixed prose remains exactly as supplied. */ }
      }
      start = Math.max(start, end - (complete ? 0 : 1))
    }
  }
  return changed ? doc.body.innerHTML : html
}
