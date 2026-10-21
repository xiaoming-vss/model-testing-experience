import { useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GeneratedCasesReviewView } from './GeneratedCasesReviewView'

vi.mock('./CaseNamesResultView', () => ({ CaseNameTreeView: () => null }))
afterEach(cleanup)

describe('候选用例表单', () => {
  it('空字段可填写，清空后重新打开仍可编辑，数组和编号保留原结构', () => {
    function Draft() {
      const [content, setContent] = useState(JSON.stringify({ cases: [{
        case_id: 'case-1', case_module: '模块', case_title: '', preconditions: [], steps: ['步骤'],
      }] }))
      const [open, setOpen] = useState(true)
      return <>
        <button onClick={() => setOpen(!open)}>切换预览</button>
        <output data-testid="draft">{content}</output>
        {open && <GeneratedCasesReviewView content={content} onChange={setContent} />}
      </>
    }
    render(<Draft />)
    fireEvent.change(screen.getByRole('textbox', { name: '用例名称' }), { target: { value: '新名称' } })
    fireEvent.change(screen.getByRole('textbox', { name: '前置条件' }), { target: { value: '条件一\n条件二' } })
    fireEvent.change(screen.getByRole('textbox', { name: '测试步骤' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: '切换预览' }))
    fireEvent.click(screen.getByRole('button', { name: '切换预览' }))
    fireEvent.change(screen.getByRole('textbox', { name: '测试步骤' }), { target: { value: '新步骤' } })
    expect(JSON.parse(screen.getByTestId('draft').textContent!).cases[0]).toEqual({
      case_id: 'case-1', case_module: '模块', case_title: '新名称',
      preconditions: ['条件一', '条件二'], steps: ['新步骤'],
    })
    expect(screen.queryByRole('textbox', { name: '用例编号' })).not.toBeInTheDocument()
  })
})
