import { useEffect, useState } from 'react'
import { Button, Image, Typography, message, type ImageProps } from 'antd'
import { downloadStoredFile } from '@/shared/api/files'

function storedFileId(path: string) {
  return /^\/v1\/files\/([a-zA-Z0-9-]+)\/download$/.exec(path)?.[1]
}

async function readFile(path: string) {
  const id = storedFileId(path)
  if (!id) throw new Error('历史文件未存入 S3，请重新执行任务')
  return downloadStoredFile(id)
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
      anchor.href = url; anchor.download = file.filename || 'download'; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) { message.error(error instanceof Error ? error.message : '下载失败') }
    finally { setBusy(false) }
  }}>{label}</Button>
}
