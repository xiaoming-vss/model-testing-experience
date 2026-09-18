import { api, listItems } from '@/services/api'
import { useEffect, useRef, useState } from 'react'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'

export function usePersonalLlmChoice(projectId?: string) {
  const [open, setOpen] = useState(false)
  const pending = useRef<{ resolve: (id: string) => void; reject: (error: Error) => void } | null>(null)
  function cancel() {
    pending.current?.reject(new Error('已取消操作'))
    pending.current = null
    setOpen(false)
  }
  useEffect(() => () => {
    pending.current?.reject(new Error('页面已关闭'))
    pending.current = null
  }, [projectId])
  async function choose() {
    if (!projectId) return Promise.reject(new Error('项目尚未加载'))
    const connections = listItems(await api.getLlmConnections(projectId)).filter(c => c.status === 'active')
    if (connections.length === 1) return connections[0].connectionId
    pending.current?.reject(new Error('已取消上一次操作'))
    setOpen(true)
    return new Promise<string>((resolve, reject) => { pending.current = { resolve, reject } })
  }
  const dialog = <LlmConnectionSelectModal key={projectId} open={open} projectId={projectId} onClose={cancel} onConfirm={id => {
    pending.current?.resolve(id)
    pending.current = null
    setOpen(false)
  }} />
  return { choose, dialog }
}
