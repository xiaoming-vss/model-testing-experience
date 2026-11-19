import { Alert, Input, Modal } from 'antd'
import shellStyles from '../styles/ui-detail-shell.module.css'
import { Text } from '../utils/detailView'
import type { UiTestSuiteCasePageModel } from '../hooks/useUiTestSuiteCasePage'

export function UiMissingVariablesModal({ page }: { page: UiTestSuiteCasePageModel }) {
  const {
    missingVariables,
    missingValues,
    setMissingValues,
    missingEnvironmentNames,
    hasMissingBuiltin,
    saveMissingVariablesMutation,
    closeMissingVariablesModal,
  } = page

  return <Modal
    className={shellStyles.scope}
    open={missingVariables.length > 0}
    title="运行前缺少变量"
    okText="保存并重新运行"
    cancelText="稍后处理"
    destroyOnHidden
    confirmLoading={saveMissingVariablesMutation.isPending}
    okButtonProps={{ disabled: hasMissingBuiltin }}
    onOk={() => saveMissingVariablesMutation.mutate()}
    onCancel={closeMissingVariablesModal}
  >
    {hasMissingBuiltin ? (
      <Alert
        showIcon
        type="warning"
        title="所选 UI 环境未配置基础地址（baseUrl），请先在环境管理中补充。"
        style={{ marginBottom: 12 }}
      />
    ) : null}
    {missingEnvironmentNames.length > 0 ? (
      <>
        <Text type="secondary">以下变量在所选 UI 环境中不存在，填写后保存到环境并重新运行。</Text>
        <div className="ui-missing-variables mt-2 flex flex-col gap-2">
          {missingEnvironmentNames.map((name) => (
            <label key={name} className="ui-missing-variable-row flex items-center gap-3">
              <span className="ui-missing-variable-name font-mono flex-[0_0_180px] overflow-hidden text-ellipsis whitespace-nowrap text-[12px]">{name}</span>
              <Input
                size="small"
                className="flex-1"
                placeholder={`请输入 ${name} 的值`}
                value={missingValues[name] ?? ''}
                onChange={(event) =>
                  setMissingValues((current) => ({ ...current, [name]: event.target.value }))
                }
              />
            </label>
          ))}
        </div>
      </>
    ) : null}
    <div className="ui-missing-variable-locations mt-4 text-[12px]">
      <Text strong>缺失位置</Text>
      <ul className="mt-2 list-disc pl-[18px] text-[var(--srf-text-muted)]">
        {missingVariables.map((item, index) => (
          <li key={`${item.caseId ?? ''}-${item.orderNo ?? ''}-${item.field ?? ''}-${item.name ?? ''}-${index}`}>
            {[item.caseName, item.stepName, item.field]
              .filter(Boolean)
              .join(' / ')}
            ：{item.name}
          </li>
        ))}
      </ul>
    </div>
  </Modal>
}
