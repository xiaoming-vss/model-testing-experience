import { useEffect, useRef, useState } from 'react'

export type RevisionAttachment = {
  fileId: string
  name: string
  previewUrl?: string
}

/** Keep uploaded images and their blob previews alive across cancel/reopen drafts. */
export function useRevisionAttachments() {
  const [attachments, setAttachments] = useState<RevisionAttachment[]>([])
  const latest = useRef(attachments)
  useEffect(() => {
    latest.current = attachments
  }, [attachments])
  useEffect(() => () => {
    latest.current.forEach(item => {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl)
    })
  }, [])
  function addAttachment(attachment: RevisionAttachment) {
    setAttachments(previous => [...previous, attachment])
  }
  function removeAttachment(fileId: string) {
    setAttachments(previous => previous.filter(item => {
      if (item.fileId !== fileId) return true
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl)
      return false
    }))
  }
  function clearAttachments() {
    setAttachments(previous => {
      previous.forEach(item => {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl)
      })
      return []
    })
  }
  return { attachments, addAttachment, removeAttachment, clearAttachments }
}
