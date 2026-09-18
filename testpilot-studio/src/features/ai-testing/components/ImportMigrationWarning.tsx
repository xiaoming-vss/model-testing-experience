import { Alert } from 'antd'

type ImportMigrationWarningProps = {
  importMigrationComplete: boolean
}

export function ImportMigrationWarning({ importMigrationComplete }: ImportMigrationWarningProps) {
  if (importMigrationComplete) return null

  return (
    <Alert
      showIcon
      type="warning"
      title="历史导入目标数据不完整"
      description="部分历史功能套件目标未能完整恢复；这不影响查看、审核或继续处理当前运行。"
    />
  )
}
