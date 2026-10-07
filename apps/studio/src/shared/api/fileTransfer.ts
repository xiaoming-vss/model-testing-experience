/** Object storage transport: bounded retries, fresh tickets, no platform credentials. */
export type DownloadTicket = { url: string; filename?: string }
const ATTEMPTS = 3

export class FileTransferError extends Error {
  readonly retryable: boolean
  constructor(message: string, retryable: boolean) {
    super(message)
    this.retryable = retryable
  }
}

export async function fileAuthorization<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation()
  } catch (error) {
    if (error instanceof TypeError) throw new FileTransferError('文件授权连接中断，请重试', true)
    if (error instanceof Error && 'status' in error && [408, 429, 500, 502, 503, 504].includes(Number(error.status))) {
      throw new FileTransferError('文件授权服务暂不可用，请重试', true)
    }
    throw error
  }
}

export function storageFailure(status: number, body = '') {
  const expired = /<(?:Code)>\s*(?:ExpiredToken|RequestExpired|RequestTimeTooSkewed)\s*<|request (?:has )?expired|expiredtoken/i.test(body)
  // A permanent S3 AccessDenied is not an expired signature. Platform errors
  // are deliberately not handled here: authorization must never be bypassed.
  const retryable = expired || [0, 408, 429, 500, 502, 503, 504].includes(status)
  return new FileTransferError(`文件传输失败（${status}），请重试`, retryable)
}

export async function retryFileTransfer<T>(operation: () => Promise<T>): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await operation()
    } catch (error) {
      if (!(error instanceof FileTransferError) || !error.retryable || attempt === ATTEMPTS - 1) throw error
      await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)))
    }
  }
}

export async function fetchSignedFile(
  authorize: () => Promise<DownloadTicket>, initialTicket?: DownloadTicket,
): Promise<{ response: Response; ticket: DownloadTicket }> {
  let first = true
  return retryFileTransfer(async () => {
    const ticket = first && initialTicket ? initialTicket : await fileAuthorization(authorize)
    first = false
    // A denied platform request exits immediately; transient failures remain bounded.
    try {
      const response = await fetch(ticket.url, { credentials: 'omit' })
      if (!response.ok) throw storageFailure(response.status, await response.text())
      // Finish reading inside the retry boundary to handle interrupted bodies too.
      const body = await response.arrayBuffer()
      return { response: new Response(body, { headers: response.headers }), ticket }
    } catch (error) {
      if (error instanceof TypeError) throw new FileTransferError('文件传输中断，请重试', true)
      throw error
    }
  })
}
