import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { GeneratedCasesReviewView } from './GeneratedCasesReviewView'

afterEach(cleanup)

describe('候选用例删除测试点', () => {
  it('删除按钮把测试点移出当前草稿并顺延选中下一条', async () => {
    function Draft() {
      const [content, setContent] = useState(JSON.stringify({ cases: [
        { case_id: 'case-a', case_module: '模块A', case_title: '用例甲', case_type: '功能测试' },
        { case_id: 'case-b', case_module: '模块A', case_title: '用例乙', case_type: '功能测试' },
      ] }))
      return <>
        <output data-testid="draft">{content}</output>
        <GeneratedCasesReviewView allowDelete content={content} onChange={setContent} />
      </>
    }
    render(<Draft />)
    // jsdom 中 React Flow 节点因缺少尺寸测量保持 hidden，无法按可访问角色找到内部按钮，直接按属性定位。
    const remove = await waitFor(() => {
      const button = document.querySelector<HTMLButtonElement>('button[aria-label="删除测试点：用例甲"]')
      if (!button) throw new Error('未渲染删除按钮')
      return button
    })
    fireEvent.click(remove)
    await waitFor(() => {
      const cases = JSON.parse(screen.getByTestId('draft').textContent!).cases as Array<{ case_title: string }>
      expect(cases.map((item) => item.case_title)).toEqual(['用例乙'])
    })
    expect(screen.getByRole('textbox', { name: '用例名称' })).toHaveValue('用例乙')
  })

  it('删除当前选中项之前的用例后保持原选中项', async () => {
    function Draft() {
      const [content, setContent] = useState(JSON.stringify({ cases: [
        { case_id: 'case-a', case_module: '模块A', case_title: '用例甲', case_type: '功能测试' },
        { case_id: 'case-b', case_module: '模块A', case_title: '用例乙', case_type: '功能测试' },
        { case_id: 'case-c', case_module: '模块A', case_title: '用例丙', case_type: '功能测试' },
      ] }))
      return <>
        <output data-testid="draft">{content}</output>
        <GeneratedCasesReviewView allowDelete content={content} onChange={setContent} />
      </>
    }
    render(<Draft />)
    const third = await waitFor(() => {
      const node = document.querySelector<HTMLElement>('[title="用例丙"]')
      if (!node) throw new Error('未渲染用例丙')
      return node
    })
    fireEvent.click(third)
    const remove = await waitFor(() => {
      const button = document.querySelector<HTMLButtonElement>('button[aria-label="删除测试点：用例甲"]')
      if (!button) throw new Error('未渲染删除按钮')
      return button
    })
    fireEvent.click(remove)
    await waitFor(() => {
      const cases = JSON.parse(screen.getByTestId('draft').textContent!).cases as Array<{ case_title: string }>
      expect(cases.map((item) => item.case_title)).toEqual(['用例乙', '用例丙'])
    })
    expect(screen.getByRole('textbox', { name: '用例名称' })).toHaveValue('用例丙')
  })

  it('只读查看时点选测试点仍重播选中动效且不显示删除', async () => {
    render(<GeneratedCasesReviewView content={JSON.stringify({ cases: [
      { case_id: 'case-a', case_module: '模块A', case_title: '用例甲', case_type: '功能测试' },
      { case_id: 'case-b', case_module: '模块A', case_title: '用例乙', case_type: '功能测试' },
    ] })} />)
    expect(document.querySelector('.ai-case-name-tree-node.point.is-selected')).toHaveClass('motion-0')
    expect(getComputedStyle(document.querySelector<HTMLElement>('.ai-case-name-tree-node.point.is-selected')!).animation).toContain('ai-case-point-select-a')
    fireEvent.click(document.querySelector<HTMLElement>('.ai-case-name-tree-node.point.is-selected')!)
    await waitFor(() => expect(document.querySelector('.ai-case-name-tree-node.point.is-selected')).toHaveClass('motion-1'))
    fireEvent.click(document.querySelector<HTMLElement>('.ai-case-name-tree-node.point.is-selected')!)
    await waitFor(() => expect(document.querySelector('.ai-case-name-tree-node.point.is-selected')).toHaveClass('motion-0'))
    expect(document.querySelector('.ai-case-name-tree-node-delete')).not.toBeInTheDocument()
  })

  it('版本阅读即使可编辑内容也不展示删除操作', () => {
    render(<GeneratedCasesReviewView onChange={() => {}} content={JSON.stringify({ cases: [
      { case_id: 'case-a', case_module: '模块A', case_title: '用例甲', case_type: '功能测试' },
    ] })} />)
    expect(document.querySelector('.ai-case-name-tree-node.point.is-selected')).toBeInTheDocument()
    expect(document.querySelector('.ai-case-name-tree-node-delete')).not.toBeInTheDocument()
  })
})
