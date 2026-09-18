import {
  CaretRightOutlined, DeleteOutlined, DownloadOutlined, EditOutlined,
  PlusOutlined, ReloadOutlined, SaveOutlined, UploadOutlined,
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
} as const

export type ActionName = keyof typeof actionRegistry
