import { api, listItems } from '@/services/api'
import { useEffect, useRef, useState } from 'react'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'

export function usePersonalLlmChoice(projectId?: string) {
  const [instruction, setInstruction] = useState('')
  const [showInstruction, setShowInstruction] = useState(false)
  const [open, setOpen] = useState(false)
  const [showCheckpointOption, setShowCheckpointOption] = useState(false)
  const [checkpointEnabled, setCheckpointEnabled] = useState(true)
  const pending = useRef<{ resolve: (choice: { connectionId: string; checkpointEnabled: boolean; instruction: string }) => void; reject: (error: Error) => void } | null>(null)
  function cancel() {
    pending.current?.reject(new Error('已取消操作'))
    pending.current = null
    setOpen(false)
  }
  useEffect(() => () => {
    pending.current?.reject(new Error('页面已关闭'))
    pending.current = null
  }, [projectId])
  async function requestChoice(withCheckpoint: boolean, withInstruction = false) {
    if (!projectId) return Promise.reject(new Error('项目尚未加载'))
    const connections = listItems(await api.getLlmConnections(projectId)).filter(c => c.status === 'active')
    if (!withCheckpoint && !withInstruction && connections.length === 1) return { connectionId: connections[0].connectionId, checkpointEnabled: false, instruction: '' }
    pending.current?.reject(new Error('已取消上一次操作'))
    setShowInstruction(withInstruction)
    setInstruction('')
    setShowCheckpointOption(withCheckpoint)
    setCheckpointEnabled(withCheckpoint)
    setOpen(true)
    return new Promise<{ connectionId: string; checkpointEnabled: boolean; instruction: string }>((resolve, reject) => { pending.current = { resolve, reject } })
  }
  async function choose() { return (await requestChoice(false)).connectionId }
  function chooseRun(withCheckpoint = true) { return requestChoice(withCheckpoint, true) }
  const dialog = <LlmConnectionSelectModal key={projectId} open={open} projectId={projectId} onClose={cancel}
    instruction={instruction} onInstructionChange={showInstruction ? setInstruction : undefined}
    showCheckpointOption={showCheckpointOption} checkpointEnabled={checkpointEnabled} onCheckpointEnabledChange={setCheckpointEnabled} onConfirm={id => {
    pending.current?.resolve({ connectionId: id, checkpointEnabled, instruction })
    pending.current = null
    setOpen(false)
  }} />
  return { choose, chooseRun, dialog }
}
