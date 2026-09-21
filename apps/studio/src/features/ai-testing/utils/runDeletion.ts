import { Modal } from 'antd'

/**
 * 运行仍在推进时 worker 可能写回结果，后端拒绝删除；这里的集合必须与其保持一致。
 * 与 runPipeline 的「进行中」不同：待审核的运行已经不占 worker，可以删除。
 */
const undeletableRunStatuses = ['pending', 'queued', 'claimed', 'running']

export function isRunDeletable(status?: string) {
  return !undeletableRunStatuses.includes((status ?? '').toLowerCase())
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
