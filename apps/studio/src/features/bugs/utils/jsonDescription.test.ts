import { expect, it } from 'vitest'
import { recognizeJsonDescription } from './jsonDescription'
const parse = (html: string) => new DOMParser().parseFromString(html, 'text/html')
it('renders complete paragraph JSON, preserving surrounding prose and numeric precision', () => {
  const html = '<h3>附件信息</h3><p>{</p><p>"id": 9007199254740993123,</p><p>"items": [0, false, null]</p><p>}</p><p>后续说明</p>'
  const result = parse(recognizeJsonDescription(html))
  expect(result.querySelector('pre code')?.textContent).toContain('9007199254740993123')
  expect(result.querySelector('pre code')?.textContent).toContain('\n  "items": [')
  expect(result.querySelector('h3')?.textContent).toBe('附件信息')
  expect(result.querySelector('p')?.textContent).toBe('后续说明')
})
it('supports br lines, independent blocks and string punctuation without interpreting HTML', () => {
  const result = parse(recognizeJsonDescription('<p>{<br>"text":"&lt;img src=x onerror=alert(1)&gt; } [",<br>"escape":"a\\"b"<br>}</p><p>说明</p><p>[1,2]</p>'))
  expect(result.querySelectorAll('pre')).toHaveLength(2)
  expect(result.querySelector('img')).toBeNull()
  expect(JSON.parse(result.querySelector('code')!.textContent!)).toHaveProperty('escape', 'a"b')
})
it.each([
  '<p>{</p><p>"a": 1,</p><p>}</p>', '<p>{"a":</p>', '<p>{"a":1} 普通说明</p>',
  '<p>说明 {"a":1}</p>', '<p>42</p>', '<p>【实际结果】</p>',
  '<pre><code>{"a":1}</code></pre>', '<p>{</p><img data-file-id="x"><p>}</p>',
  '<p><strong>{"a":1}</strong></p>', '<ul><li><p>{"a":1}</p></li></ul>',
])('keeps incomplete JSON, prose, existing code and rich content unchanged: %s', html => {
  expect(recognizeJsonDescription(html)).toBe(html)
})
