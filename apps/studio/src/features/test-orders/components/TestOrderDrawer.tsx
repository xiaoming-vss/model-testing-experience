import { Button, Drawer, Form, Input, Select, Space } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import type { CreateTestOrderPayload, TestOrder } from '../types'

type FormValues = {
  sprintId: string
  name: string
  testedVersion?: string
  sourceOrderId?: string
}

type Props = {
  open: boolean
  order?: TestOrder | null
  projectId?: string
  sprintOptions: Array<{ label: string; value: string }>
  defaultSprintId?: string | null
  onClose: () => void
  onSaved?: (order: TestOrder) => void
}

export function TestOrderDrawer({
  open,
  order,
  projectId,
  sprintOptions,
  defaultSprintId,
  onClose,
  onSaved,
}: Props) {
  const [form] = Form.useForm<FormValues>()
  const queryClient = useQueryClient()
  const isEdit = Boolean(order?.orderId)

  const sourceOrdersQuery = useQuery({
    queryKey: ['testOrders', projectId, 'forRetest'],
    queryFn: () => api.getProjectTestOrders(projectId!),
    enabled: open && !isEdit && Boolean(projectId),
  })
  const sourceOptions = useMemo(
    () =>
      listItems(sourceOrdersQuery.data).map((item) => ({
        label: `${item.name}${item.testedVersion ? ` · ${item.testedVersion}` : ''}`,
        value: item.orderId!,
      })),
    [sourceOrdersQuery.data],
  )

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      sprintId: order?.sprintId ?? defaultSprintId ?? undefined,
      name: order?.name ?? '',
      testedVersion: order?.testedVersion ?? '',
      sourceOrderId: undefined,
    })
  }, [defaultSprintId, form, open, order])

  const saveMutation = useMutation({
    mutationFn: (values: FormValues) => {
      const payload: CreateTestOrderPayload = {
        name: values.name.trim(),
        testedVersion: (values.testedVersion ?? '').trim(),
      }
      if (order?.orderId) return api.updateTestOrder(order.orderId, payload)
      return api.createTestOrder(values.sprintId, {
        ...payload,
        sourceOrderId: values.sourceOrderId ?? '',
      })
    },
    onSuccess: (saved) => {
      message.success(isEdit ? '测试单已更新' : '测试单已创建')
      queryClient.invalidateQueries({ queryKey: ['testOrders'] })
      onSaved?.(saved)
      onClose()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  return (
    <Drawer
      title={isEdit ? '编辑测试单' : '新建测试单'}
      open={open}
      onClose={onClose}
      size={520}
      extra={
        <Button
          type="primary"
          className="action-btn-save"
          loading={saveMutation.isPending}
          onClick={() => form.submit()}
        >
          {saveMutation.isPending ? '保存中...' : '保存'}
        </Button>
      }
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => saveMutation.mutate(values)}
      >
        <Form.Item
          label="所属迭代"
          name="sprintId"
          rules={[{ required: true, message: '请选择迭代' }]}
        >
          <Select options={sprintOptions} placeholder="请选择迭代" disabled={isEdit} />
        </Form.Item>
        <Form.Item
          label="测试单名称"
          name="name"
          rules={[{ required: true, message: '请输入测试单名称' }]}
        >
          <Input placeholder="例如：V2.3 回归测试单" maxLength={100} />
        </Form.Item>
        <Form.Item label="被测版本" name="testedVersion">
          <Input placeholder="例如：V2.3.1-rc2" maxLength={100} />
        </Form.Item>
        {!isEdit ? (
          <Form.Item
            label="从已有测试单带入（重测）"
            name="sourceOrderId"
            extra="只带入结果非「通过」的条目，新测试单从「未执行」开始；不保留与来源单的关联。"
          >
            <Select
              allowClear
              placeholder="不带入"
              options={sourceOptions}
              loading={sourceOrdersQuery.isLoading}
            />
          </Form.Item>
        ) : null}
        <Space size={4}>
          <span className="hint">测试单归属于一个迭代；用例从用例库挑选后加入。</span>
        </Space>
      </Form>
    </Drawer>
  )
}
