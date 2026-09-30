/** 只对独立的标准章节标题分区；未知内容原样保留，不改写保存的数据。 */
export function splitBugDescription(html: string) {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const sections: { title: string; html: string; kind: string }[] = []
  const kinds: Record<string, string> = { 前置条件: 'context', 环境信息: 'context', 复现步骤: 'steps', 实际结果: 'actual', 预期结果: 'expected' }
  for (const node of Array.from(doc.body.childNodes)) {
    const text = node.textContent?.trim().replace(/^【|】$/g, '') ?? ''
    const heading = node instanceof Element && /^(H[1-6]|P)$/.test(node.tagName) && !node.querySelector('img,video,table') && kinds[text]
    if (heading) sections.push({ title: text, html: '', kind: kinds[text] })
    else {
      if (!sections.length) sections.push({ title: '', html: '', kind: 'content' })
      sections[sections.length - 1].html += node instanceof Element ? node.outerHTML : new XMLSerializer().serializeToString(node)
    }
  }
  return sections
}

