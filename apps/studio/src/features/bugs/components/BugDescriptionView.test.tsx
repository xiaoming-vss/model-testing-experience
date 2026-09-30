import { expect, it } from 'vitest'
import { splitBugDescription } from '../utils/splitBugDescription'
it('识别模板章节并完整保留截图和列表', () => {
  const sections = splitBugDescription('<p><strong>【实际结果】</strong></p><p>异常<img data-file-id="f"></p><h3>预期结果</h3><ol><li>正常</li></ol>')
  expect(sections.map((item) => item.kind)).toEqual(['actual', 'expected'])
  expect(sections[0].html).toContain('data-file-id="f"')
  expect(sections[1].html).toContain('<ol><li>正常</li></ol>')
})
it('不丢弃未知标题、普通文字和带图标题', () => {
  const html = '<h2>调查结论</h2><p>实际结果<img data-file-id="f"></p><p>其他内容</p>'
  expect(splitBugDescription(html)).toEqual([{ title: '', kind: 'content', html }])
})
