import { useEffect, useState } from 'react'
import { downloadStoredFile } from '@/shared/api/files'

/** Keep signed URLs out of the DOM; completed Blob URLs survive signature expiry. */
export function useStoredFileUrls(fileIds: string[]) {
  const key = [...new Set(fileIds)].join(',')
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState<{ key: string; sources: Record<string, string>; errors: Record<string, string> }>({ key: '', sources: {}, errors: {} })
  useEffect(() => {
    let cancelled = false
    const urls: string[] = []
    setState({ key, sources: {}, errors: {} })
    for (const fileId of key ? key.split(',') : []) {
      void downloadStoredFile(fileId).then(({ blob }) => {
        if (cancelled) return
        const url = URL.createObjectURL(blob)
        urls.push(url)
        setState((previous) => ({ ...previous, sources: { ...previous.sources, [fileId]: url } }))
      }).catch((error: unknown) => {
        if (!cancelled) setState((previous) => ({ ...previous, errors: { ...previous.errors, [fileId]: error instanceof Error ? error.message : '文件加载失败' } }))
      })
    }
    return () => { cancelled = true; urls.forEach((url) => URL.revokeObjectURL(url)) }
  }, [key, revision])
  return { ...(state.key === key ? state : { key, sources: {}, errors: {} }), reload: () => setRevision((value) => value + 1) }
}
