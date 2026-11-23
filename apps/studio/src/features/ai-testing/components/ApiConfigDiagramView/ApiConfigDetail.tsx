import { CopyOutlined, KeyOutlined, LockOutlined, RightOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { useId } from 'react'
import type { ApiConfigCaseView } from '../../utils/apiConfigDiagram'
import type { ApiConfigContractView } from '../../utils/apiConfigContract'
import { ApiConfigFieldTable } from './ApiConfigFieldTable'
import { ApiConfigRequestSection, type ApiConfigRequestGroup } from './ApiConfigRequestSection'
import { ApiConfigRuleSection } from './ApiConfigRuleSection'
import styles from '../../styles/api-config.module.css'
import {
  AUTH_CHIP,
  COPY_BUTTON,
  DETAIL_FOOT,
  DETAIL_HEAD,
  DETAIL_PANEL,
  DETAIL_TITLE,
  KEY_CHIP,
  KEY_CHIP_BUTTON,
  KEY_NOTE,
  META_ROW,
  META_SEP,
  METHOD_BASE,
  ORDER_TEXT,
  PATH_CODE,
  PATH_VARIABLE,
  SECTION,
  SECTION_COUNT,
  SECTION_DESC,
  SECTION_HEAD,
  SECTION_KEY,
  SECTION_TITLE,
  SIGNAL_EMPTY,
  SIGNAL_GRID,
  SIGNAL_ITEM,
  SIGNAL_LABEL,
  SIGNAL_VALUE,
  STRONG_TEXT,
  TITLE_ROW,
  VAR_CHIP,
  methodTone,
} from './apiConfigClasses'

function PathText({ path }: { path: string }) {
  return <>{path.split(/(\{\{[^}]+\}\}|\{[^}]+\})/g).map((part, index) => {
    const isVariable = /^\{\{[^}]+\}\}$|^\{[^}]+\}$/.test(part)
    return isVariable ? <span key={`${part}-${index}`} className={PATH_VARIABLE}>{part}</span> : <span key={`${part}-${index}`}>{part}</span>
  })}</>
}

export function ApiConfigDetail({ apiCase, contract, showRules, collapsible, collapsed, onToggleCollapsed, onCopyPath, onJumpToKey, collapsedPaths, onTogglePath, idPrefix }: {
  apiCase: ApiConfigCaseView
  contract: ApiConfigContractView
  showRules: boolean
  collapsible: boolean
  collapsed: boolean
  onToggleCollapsed: () => void
  onCopyPath: () => void
  onJumpToKey: (path: string) => void
  collapsedPaths: Set<string>
  onTogglePath: (path: string) => void
  idPrefix: string
}) {
  const responseTitleId = useId()
  const groups: ApiConfigRequestGroup[] = [
    ...(contract.headers.length ? [{ key: 'headers', title: '请求头', rows: contract.headers, variant: 'header' as const }] : []),
    ...(contract.pathParams.length ? [{ key: 'path', title: 'Path', rows: contract.pathParams, variant: 'field' as const }] : []),
    ...(contract.query.length ? [{ key: 'query', title: 'Query', rows: contract.query, variant: 'field' as const }] : []),
    ...(contract.body.length || contract.rawBody ? [{
      key: 'body',
      title: contract.bodyLabel,
      rows: contract.body,
      variant: 'field' as const,
      ...(contract.rawBody ? { rawBody: contract.rawBody } : {}),
    }] : []),
  ]
  const markedKeyCount = contract.keyExtractions.length
  const hasRuleKeys = showRules && apiCase.extractRules.length > 0
  const keyCount = showRules ? apiCase.extractRules.length || markedKeyCount : markedKeyCount
  const keyNote = !showRules && contract.keyExtractions.length === 1 ? contract.keyExtractions[0].description : ''
  const toggleLabel = `${collapsed ? '展开' : '收起'} ${apiCase.method} ${apiCase.name}`

  return <section aria-label="接口详情" className={DETAIL_PANEL}>
    <header className={DETAIL_HEAD}>
      <div className={TITLE_ROW}>
        {collapsible ? <button type="button" className={COPY_BUTTON} aria-expanded={!collapsed} aria-label={toggleLabel} onClick={onToggleCollapsed}>
          <RightOutlined className={`${styles.chevron}${collapsed ? '' : ` ${styles.chevronOpen}`} text-[11px]`} aria-hidden />
        </button> : null}
        <span className={`${METHOD_BASE} ${methodTone(apiCase.method)}`}>{apiCase.method}</span>
        <h2 className={DETAIL_TITLE}>{apiCase.name}</h2>
        {apiCase.orderNo ? <span className={ORDER_TEXT}>#{apiCase.orderNo}</span> : null}
        {!collapsed ? <button type="button" className={COPY_BUTTON} aria-label="复制接口路径" title="复制接口路径" onClick={onCopyPath}>
          <CopyOutlined aria-hidden />
        </button> : null}
      </div>
      {!collapsed ? <>
        <div className="mt-2">
          <code className={PATH_CODE}><PathText path={apiCase.path} /></code>
        </div>
        <div className={META_ROW}>
          <span><b className={STRONG_TEXT}>{contract.requestFieldCount}</b> 请求字段</span>
          <span className={META_SEP} aria-hidden />
          <span><b className={STRONG_TEXT}>{contract.responseFieldCount}</b> 响应字段</span>
          <span className={META_SEP} aria-hidden />
          <span>认证头 <b className={STRONG_TEXT}>{contract.authHeader ? 1 : 0}</b></span>
        </div>
      </> : null}
    </header>

    {!collapsed ? <>
      <div className={SIGNAL_GRID} aria-label="契约摘要">
        <div className={SIGNAL_ITEM}>
          <span className={SIGNAL_LABEL}>变量依赖</span>
          <div className={SIGNAL_VALUE}>{apiCase.usedVariables.length
            ? apiCase.usedVariables.map((variable) => <span key={variable} className={VAR_CHIP}>{variable}</span>)
            : <span className={SIGNAL_EMPTY}>无</span>}</div>
        </div>
        <div className={SIGNAL_ITEM}>
          <span className={SIGNAL_LABEL}>关键提取</span>
          <div className={SIGNAL_VALUE}>
            {hasRuleKeys ? apiCase.extractRules.map((rule, index) => <span key={`${rule.name}-${index}`} className={KEY_CHIP} title={rule.detail}>{rule.name}</span>)
              : contract.keyExtractions.map((row) => <button key={row.path} type="button" className={KEY_CHIP_BUTTON} title={row.description || row.path}
                onClick={() => onJumpToKey(row.path)}>{row.path}</button>)}
            {!keyCount ? <span className={SIGNAL_EMPTY}>无</span> : null}
            {keyNote ? <span className={KEY_NOTE}>{keyNote}</span> : null}
          </div>
        </div>
        <div className={SIGNAL_ITEM}>
          <span className={SIGNAL_LABEL}>认证头</span>
          <div className={SIGNAL_VALUE}>{contract.authHeader
            ? <span className={AUTH_CHIP} title={contract.authHeader.value}><SafetyCertificateOutlined aria-hidden />{contract.authHeader.name}</span>
            : <span className={SIGNAL_EMPTY}>未提取</span>}</div>
        </div>
      </div>

      {groups.length ? <ApiConfigRequestSection groups={groups} caseKey={apiCase.key} idPrefix={idPrefix}
        collapsedPaths={collapsedPaths} onTogglePath={onTogglePath} /> : null}

      {contract.response.length ? <section className={SECTION} aria-labelledby={responseTitleId}>
        <header className={SECTION_HEAD}>
          <h2 id={responseTitleId} className={SECTION_TITLE}>响应</h2>
          <span className={SECTION_COUNT}>{contract.responseFieldCount} 个字段</span>
          <span className={SECTION_DESC}>{keyCount ? `${keyCount} 个关键提取` : '无关键提取'}</span>
          {markedKeyCount ? <span className={SECTION_KEY}><KeyOutlined aria-hidden />关键字段已标记</span> : null}
        </header>
        <ApiConfigFieldTable rows={contract.response} variant="field" label="响应字段" caseKey={apiCase.key} section="response"
          idPrefix={idPrefix} collapsedPaths={collapsedPaths} onTogglePath={onTogglePath} />
      </section> : null}

      {showRules ? <ApiConfigRuleSection extractRules={apiCase.extractRules} assertRules={apiCase.assertRules} /> : null}

      <div className={DETAIL_FOOT}><LockOutlined aria-hidden />提取结果为只读契约，生成用例时按此字段结构执行。</div>
    </> : null}
  </section>
}
