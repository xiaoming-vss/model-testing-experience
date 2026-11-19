export type RequestAuthBridge = {
  getToken: () => string | null
  onUnauthorized: () => void
}

const anonymousBridge: RequestAuthBridge = {
  getToken: () => null,
  onUnauthorized: () => undefined,
}

let bridge = anonymousBridge

export function configureRequestAuth(next: RequestAuthBridge) {
  bridge = next
}

export function resetRequestAuth() {
  bridge = anonymousBridge
}

export function getRequestToken() {
  return bridge.getToken()
}

export function notifyRequestUnauthorized() {
  bridge.onUnauthorized()
}
