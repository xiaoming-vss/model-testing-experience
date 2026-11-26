import { Modal } from 'antd'
import { isRunWorkerActive } from '@/domain/runs/status'

/** 后端只拒绝 worker 仍可能写回结果的运行；待审核已经不占 worker，可以删除。 */
export function isRunDeletable(status?: string) {
  return !isRunWorkerActive(status)
}

/** 运行记录是硬删除：审核与导入痕迹一并消失，导入产生的正式资产保留。 */
export function confirmDeleteRun(onConfirm: () => void) {
  Modal.confirm({
    mask: { closable: false },
    title: '确认删除该运行记录？',
    content: '删除后无法恢复；本次运行导入产生的正式资产会保留。',
    okText: '删除',
    okButtonProps: { danger: true },
    cancelText: '取消',
    onOk: onConfirm,
  })
}
