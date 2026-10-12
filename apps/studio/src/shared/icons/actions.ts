import {
  CaretRightOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, LinkOutlined,
  PlusOutlined, ReloadOutlined, SaveOutlined, SyncOutlined, UploadOutlined,
} from '@ant-design/icons'

export const actionRegistry = {
  create: { label: '新建', Icon: PlusOutlined },
  run: { label: '运行', Icon: CaretRightOutlined },
  edit: { label: '编辑', Icon: EditOutlined },
  delete: { label: '删除', Icon: DeleteOutlined },
  save: { label: '保存', Icon: SaveOutlined },
  refresh: { label: '刷新', Icon: ReloadOutlined },
  download: { label: '下载', Icon: DownloadOutlined },
  upload: { label: '上传', Icon: UploadOutlined },
  bind: { label: '绑定', Icon: LinkOutlined },
  sync: { label: '同步', Icon: SyncOutlined },
} as const

export type ActionName = keyof typeof actionRegistry
