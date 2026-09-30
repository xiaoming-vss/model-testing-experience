import { describe, expect, it } from 'vitest'
import { extractRichTextFileIds, injectImageSources, stripImageSources } from './utils'

describe('富文本存储值工具', () => {
  it('按出现顺序去重提取 data-file-id', () => {
    const html =
      '<p>现象</p><img data-file-id="file-2"><img data-file-id="file-1"><img data-file-id="file-2">'
    expect(extractRichTextFileIds(html)).toEqual(['file-2', 'file-1'])
    expect(extractRichTextFileIds('<p>无图片</p>')).toEqual([])
  })

  it('输出前剥掉预览 src，只保留 data-file-id', () => {
    const html =
      '<img src="https://minio.local/signed?x=1" data-file-id="file-1" alt="截图"><p>保留</p>'
    expect(stripImageSources(html)).toBe('<img data-file-id="file-1" alt="截图"><p>保留</p>')
  })

  it('渲染前注入签名地址', () => {
    const html = '<img data-file-id="file-1">'
    expect(injectImageSources(html, { 'file-1': 'https://signed/url' })).toBe(
      '<img data-file-id="file-1" src="https://signed/url">',
    )
  })
})
