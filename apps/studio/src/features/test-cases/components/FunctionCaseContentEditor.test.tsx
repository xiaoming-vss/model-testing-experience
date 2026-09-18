import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Button, Form } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FunctionCaseContentEditor } from './FunctionCaseContentEditor'

describe('FunctionCaseContentEditor', () => {
  afterEach(cleanup)
  it('shows existing content in three fields and preserves untouched step pairs', async () => {
    const submit = vi.fn()
    const content = { preconditions: ['已登录', '设备在线'], steps: [
      { action: '打开\n保持多行', expected: '显示页面' },
      { action: '保存', expected: '保存成功' },
    ] }
    render(<Form initialValues={{ content }} onFinish={submit}>
      <FunctionCaseContentEditor /><Button htmlType="submit">保存用例</Button>
    </Form>)
    expect(screen.getAllByRole('textbox')).toHaveLength(3)
    expect(screen.getByRole('textbox', { name: '前置条件' })).toHaveValue('已登录\n设备在线')
    expect(screen.getByRole('textbox', { name: '操作步骤' })).toHaveValue('打开\n保持多行\n保存')
    expect(screen.getByRole('textbox', { name: '预期结果' })).toHaveValue('显示页面\n保存成功')
    expect(screen.queryByRole('button', { name: /添加步骤|上移|下移|删除步骤/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '保存用例' }))
    await waitFor(() => expect(submit).toHaveBeenCalledWith({ content }))
  })

  it('saves multiline inputs as paired steps and supports clearing both fields', async () => {
    const submit = vi.fn()
    render(<Form initialValues={{ content: { preconditions: [], steps: [] } }} onFinish={submit}>
      <FunctionCaseContentEditor /><Button htmlType="submit">保存用例</Button>
    </Form>)
    fireEvent.change(screen.getByRole('textbox', { name: '前置条件' }), { target: { value: '设备在线\n已登录' } })
    fireEvent.change(screen.getByRole('textbox', { name: '操作步骤' }), { target: { value: '打开\n保存' } })
    fireEvent.change(screen.getByRole('textbox', { name: '预期结果' }), { target: { value: '显示页面\n保存成功' } })
    fireEvent.click(screen.getByRole('button', { name: '保存用例' }))
    await waitFor(() => expect(submit).toHaveBeenCalledWith({ content: {
      preconditions: ['设备在线\n已登录'], steps: [{ action: '打开', expected: '显示页面' }, { action: '保存', expected: '保存成功' }],
    } }))
    fireEvent.change(screen.getByRole('textbox', { name: '操作步骤' }), { target: { value: '' } })
    expect(screen.getByRole('textbox', { name: '预期结果' })).toHaveValue('显示页面\n保存成功')
    fireEvent.change(screen.getByRole('textbox', { name: '预期结果' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: '保存用例' }))
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2))
    expect(submit.mock.calls[1][0].content.steps).toEqual([])
  })
})
