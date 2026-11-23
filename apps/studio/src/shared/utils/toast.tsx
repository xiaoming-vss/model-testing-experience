import { CheckCircleFilled, CloseCircleFilled, CloseOutlined, ExclamationCircleFilled, InfoCircleFilled } from '@ant-design/icons'
import type { ReactNode } from 'react'
import styles from '@/shared/styles/notify.module.css'
import { randomId } from './crypto'
import { message } from './feedback'

export type ToastKind = 'success' | 'error' | 'warning' | 'info'
export type ToastOptions = {
  title: ReactNode
  description?: ReactNode
  duration?: number
  key?: string
}

const icons: Record<ToastKind, ReactNode> = {
  success: <CheckCircleFilled aria-hidden />,
  error: <CloseCircleFilled aria-hidden />,
  warning: <ExclamationCircleFilled aria-hidden />,
  info: <InfoCircleFilled aria-hidden />,
}

function show(kind: ToastKind, options: ToastOptions | string) {
  const { title, description, duration = kind === 'error' ? 6 : 4.8, key } = typeof options === 'string' ? { title: options } : options
  const id = key ?? `app-notify-${randomId()}`
  message.open({
    key: id,
    duration,
    className: `${styles.notice} ${styles[kind]}`,
    content: <span className={styles.card} role={kind === 'error' ? 'alert' : 'status'}>
      <span className={styles.icon}>{icons[kind]}</span>
      <span className={styles.copy}><strong>{title}</strong>{description ? <span>{description}</span> : null}</span>
      <button type="button" className={styles.close} aria-label="关闭提示" onClick={() => message.destroy(id)}><CloseOutlined aria-hidden /></button>
      <i className={styles.progress} style={{ animationDuration: `${duration}s` }} aria-hidden />
    </span>,
  })
}

/** 顶部居中、可自动消失的瞬时反馈；阻塞错误仍留在页面内联展示。 */
export const notify = {
  success: (options: ToastOptions | string) => show('success', options),
  error: (options: ToastOptions | string) => show('error', options),
  warning: (options: ToastOptions | string) => show('warning', options),
  info: (options: ToastOptions | string) => show('info', options),
}
