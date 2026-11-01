import { api, listItems } from '@/services/api'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'

export function usePersonalLlmChoice(projectId?: string, runOptions?: {
  render: (open: boolean) => ReactNode
  confirmDisabled: boolean
}) {
  const [instruction, setInstruction] = useState('')
  const [showInstruction, setShowInstruction] = useState(false)
  const [instructionCopy, setInstructionCopy] = useState<{ label?: string; placeholder?: string }>({})
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
  async function requestChoice(withCheckpoint: boolean, withInstruction = false, alwaysConfirm = false) {
    if (!projectId) return Promise.reject(new Error('项目尚未加载'))
    if (!alwaysConfirm) {
      const connections = listItems(await api.getLlmConnections(projectId)).filter(c => c.status === 'active')
      if (!withCheckpoint && !withInstruction && connections.length === 1) return { connectionId: connections[0].connectionId, checkpointEnabled: false, instruction: '' }
    }
    pending.current?.reject(new Error('已取消上一次操作'))
    setShowInstruction(withInstruction)
    setInstruction('')
    setShowCheckpointOption(withCheckpoint)
    setCheckpointEnabled(withCheckpoint)
    setOpen(true)
    return new Promise<{ connectionId: string; checkpointEnabled: boolean; instruction: string }>((resolve, reject) => { pending.current = { resolve, reject } })
  }
  async function choose(options?: { alwaysConfirm?: boolean }) { return (await requestChoice(false, false, options?.alwaysConfirm)).connectionId }
  function chooseRun(withCheckpoint = true, copy: { label?: string; placeholder?: string } = {}) { setInstructionCopy(copy); return requestChoice(withCheckpoint, true) }
  const dialog = <LlmConnectionSelectModal key={projectId} open={open} projectId={projectId} onClose={cancel}
    confirmDisabled={showInstruction && runOptions?.confirmDisabled}
    instruction={instruction} instructionLabel={instructionCopy.label} instructionPlaceholder={instructionCopy.placeholder} onInstructionChange={showInstruction ? setInstruction : undefined}
    showCheckpointOption={showCheckpointOption} checkpointEnabled={checkpointEnabled} onCheckpointEnabledChange={setCheckpointEnabled} onConfirm={id => {
    pending.current?.resolve({ connectionId: id, checkpointEnabled, instruction })
    pending.current = null
    setOpen(false)
  }}>{showInstruction ? runOptions?.render(open) : null}</LlmConnectionSelectModal>
  return { choose, chooseRun, dialog }
}
