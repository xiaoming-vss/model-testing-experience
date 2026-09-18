import type { MessageInstance } from 'antd/es/message/interface'

let boundMessage: MessageInstance | null = null

export function bindFeedbackMessage(messageApi: MessageInstance) {
  boundMessage = messageApi
}

function getMessage() {
  if (!boundMessage) {
    throw new Error('Feedback message API is not bound')
  }
  return boundMessage
}

export const message: MessageInstance = {
  info: (...args) => getMessage().info(...args),
  success: (...args) => getMessage().success(...args),
  error: (...args) => getMessage().error(...args),
  warning: (...args) => getMessage().warning(...args),
  loading: (...args) => getMessage().loading(...args),
  open: (...args) => getMessage().open(...args),
  destroy: (...args) => getMessage().destroy(...args),
}
