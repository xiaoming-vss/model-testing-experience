import { useEffect, useState } from 'react'
import { Button, Image, Typography, message, type ImageProps } from 'antd'
import { request } from '@/shared/api/request'

function storedFileId(path: string) {
  return /^\/v1\/files\/([a-zA-Z0-9-]+)\/download$/.exec(path)?.[1]
}

async function readFile(path: string) {
  const id = storedFileId(path)
  if (!id) throw new Error('历史文件未存入 S3，请重新执行任务')
  const ticket = await request<{ url: string; filename: string }>(`/v1/files/${id}/download`)
  const response = await fetch(ticket.url, { credentials: 'omit' })
  if (!response.ok) throw new Error('文件下载失败，请重试')
  return { blob: await response.blob(), filename: ticket.filename }
}

export function StoredImage({ src = '', ...props }: ImageProps) {
  const [value, setValue] = useState<{ path: string; url?: string; error?: string }>()
  useEffect(() => {
    let canceled = false
    let objectUrl = ''
    readFile(src).then(({ blob }) => {
      objectUrl = URL.createObjectURL(blob)
      if (canceled) URL.revokeObjectURL(objectUrl)
      else setValue({ path: src, url: objectUrl })
    }).catch((error: Error) => {
      if (!canceled) setValue({ path: src, error: error.message })
    })
    return () => { canceled = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [src])
  if (value?.path !== src) return <Typography.Text type="secondary">加载截图…</Typography.Text>
  if (!value.url) return <Typography.Text type="secondary">{value.error}</Typography.Text>
  return <Image {...props} src={value.url} />
}

export function StoredFileDownload({ path, label = '下载文件' }: { path: string; label?: string }) {
  const [busy, setBusy] = useState(false)
  return <Button type="link" size="small" loading={busy} onClick={async () => {
    setBusy(true)
    try {
      const file = await readFile(path)
      const url = URL.createObjectURL(file.blob)
      const anchor = document.createElement('a')
      anchor.href = url; anchor.download = file.filename; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) { message.error(error instanceof Error ? error.message : '下载失败') }
    finally { setBusy(false) }
  }}>{label}</Button>
}
