import { KeyOutlined, RightOutlined } from '@ant-design/icons'
import type { ApiConfigFieldView } from '../../utils/apiConfigContract'
import styles from '../../styles/api-config.module.css'
import {
  CODE_CHIP,
  CODE_CHIP_CODE,
  CONTAINER_CHIP,
  FIELD_CODE,
  FIELD_COLUMNS,
  FIELD_DESCRIPTION,
  FIELD_EMPTY,
  FIELD_HEAD_BASE,
  FIELD_META,
  FIELD_NAME,
  FIELD_ROW_BASE,
  FIELD_ROW_KEY,
  HEADER_COLUMNS,
  KEY_FLAG,
  KEY_ICON,
  OBJECT_TOGGLE,
  OPTIONAL_FLAG,
  REQUIRED_FLAG,
  TYPE_CHIP,
  VALUE_CHIP,
  apiConfigFieldId,
} from './apiConfigClasses'

const NAME_CELL = 'min-w-0 max-[640px]:col-span-2'

export function ApiConfigFieldTable({ rows, variant, label, caseKey, section, idPrefix, collapsedPaths, onTogglePath }: {
  rows: ApiConfigFieldView[]
  variant: 'header' | 'field'
  label: string
  caseKey: string
  section: string
  idPrefix: string
  collapsedPaths: Set<string>
  onTogglePath: (path: string) => void
}) {
  const columns = variant === 'header' ? HEADER_COLUMNS : FIELD_COLUMNS
  const visibleRows = rows.filter((row) => !row.ancestorPaths.some((path) => collapsedPaths.has(path)))

  if (!visibleRows.length) {
    return <p className={`m-0 py-2 ${FIELD_EMPTY}`}>未提取到{variant === 'header' ? '请求头' : '字段'}。</p>
  }

  return <div className="min-w-0" role="table" aria-label={label}>
    <div className={`${FIELD_HEAD_BASE} ${columns}`} role="row">
      <span role="columnheader">{variant === 'header' ? '请求头' : '字段'}</span>
      <span role="columnheader">{variant === 'header' ? '值' : '类型'}</span>
      <span role="columnheader">{variant === 'header' ? '说明' : '约束与说明'}</span>
    </div>
    <div className="flex flex-col" role="rowgroup">
      {visibleRows.map((row) => {
        const isContainer = row.kind !== 'field'
        const collapsed = collapsedPaths.has(row.path)
        const hasMeta = Boolean(row.required || row.optional || row.defaultValue || row.enumValue || row.constraints.length || row.keyExtraction || row.description)
        return <div key={row.key} id={apiConfigFieldId(idPrefix, caseKey, section, row.path)} role="row" data-field-path={row.path}
          className={`${FIELD_ROW_BASE} ${columns}${row.keyExtraction ? ` ${FIELD_ROW_KEY}` : ''}`}>
          <div role="cell" className={NAME_CELL}>
            <div className={FIELD_NAME} style={{ paddingLeft: row.depth * 16 }}>
              {isContainer ? <button type="button" className={OBJECT_TOGGLE} aria-expanded={!collapsed}
                aria-label={`${collapsed ? '展开' : '收起'} ${row.path}`} onClick={() => onTogglePath(row.path)}>
                <RightOutlined className={`${styles.chevron}${collapsed ? '' : ` ${styles.chevronOpen}`} text-[10px]`} aria-hidden />
                <code className={FIELD_CODE} title={row.path}>{row.name}</code>
              </button> : <>
                {row.keyExtraction ? <KeyOutlined className={KEY_ICON} aria-hidden /> : null}
                <code className={FIELD_CODE} title={row.path}>{row.name}</code>
              </>}
            </div>
          </div>
          <div role="cell" className="min-w-0">
            {variant === 'header'
              ? <code className={VALUE_CHIP} title={row.value || undefined}>{row.value || '—'}</code>
              : <span className={isContainer ? CONTAINER_CHIP : TYPE_CHIP}>{row.type || '—'}</span>}
          </div>
          <div role="cell" className="min-w-0">
            {isContainer ? <span className={FIELD_EMPTY}>{row.childCount ? `${row.childCount} 个字段` : '空对象'}</span> : <div className={FIELD_META}>
              {row.required ? <span className={REQUIRED_FLAG}>必传</span> : row.optional ? <span className={OPTIONAL_FLAG}>可选</span> : null}
              {row.defaultValue ? <span className={CODE_CHIP}><span>默认</span><code className={CODE_CHIP_CODE}>{row.defaultValue}</code></span> : null}
              {row.enumValue ? <span className={CODE_CHIP}><span>枚举</span><code className={CODE_CHIP_CODE}>{row.enumValue}</code></span> : null}
              {variant === 'field' && row.type === 'value' && row.value
                ? <span className={CODE_CHIP}><code className={CODE_CHIP_CODE}>{row.value}</code></span> : null}
              {row.constraints.map((constraint) => <span key={constraint} className={CODE_CHIP}><code className={CODE_CHIP_CODE}>{constraint}</code></span>)}
              {row.keyExtraction ? <span className={KEY_FLAG}><KeyOutlined aria-hidden />关键提取</span> : null}
              {row.description ? <span className={FIELD_DESCRIPTION}>{row.description}</span> : null}
              {!hasMeta && !(variant === 'field' && row.type === 'value' && row.value)
                ? <span className={FIELD_EMPTY}>{variant === 'header' ? '—' : '无约束'}</span> : null}
            </div>}
          </div>
        </div>
      })}
    </div>
  </div>
}
