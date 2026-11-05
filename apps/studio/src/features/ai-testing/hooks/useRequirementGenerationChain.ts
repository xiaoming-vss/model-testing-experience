import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { message } from '@/shared/utils/feedback'
import { UNSAVED_NAVIGATION_EVENT } from '@/shared/utils/unsavedChanges'
import { usePendingRequestId } from '@/shared/hooks/usePendingRequestId'
import { getErrorMessage } from '@/utils/format'
import { RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import {
  generationChainApi,
  type GenerationChain,
  type GenerationChainKind,
  type GenerationChainStage,
  type GenerationChainVersionDetail,
} from '../api/generationChain.api'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'
import { useRevisionAttachments } from './useRevisionAttachments'
import { buildRevisionTemplate, getRevisionQuestions } from '../utils/functionalRevision'

export type ChainFilter = 'all' | 'draft' | 'empty'
export type ChainArtifactMode = 'visual' | 'raw'

export type SelectedChainStage = { kind: GenerationChainKind; stage: string }

type ReviewAction = 'approve' | 'reject'

export function useRequirementGenerationChain({
  requirementId,
  projectId,
  enabled,
}: {
  requirementId: string
  projectId: string
  enabled: boolean
}) {
  const client = useQueryClient()
  const [selected, setSelected] = useState<SelectedChainStage>()
  const [filter, setFilter] = useState<ChainFilter>('all')
  const [mode, setMode] = useState<ChainArtifactMode>('visual')
  const [versionKey, setVersionKey] = useState('')
  const [editing, setEditing] = useState<{ content: string; original: string; attemptId: string }>()
  const [diffOpen, setDiffOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [revisionOpen, setRevisionOpen] = useState(false)
  const [revisionInstruction, setRevisionInstruction] = useState('')
  const [revisionTemplate, setRevisionTemplate] = useState('')
  const revisionDraftKey = useRef('')
  const revisionAttachments = useRevisionAttachments()
  const [upstream, setUpstream] = useState<Record<string, string>>({})
  const [importOpen, setImportOpen] = useState(false)
  const [importTargetId, setImportTargetId] = useState('')
  const [importConflicts, setImportConflicts] = useState<Record<string, unknown>[]>([])
  const personalLlm = usePersonalLlmChoice(projectId)
  const pendingRun = usePendingRequestId()
  const pendingRevision = usePendingRequestId()
  const pendingReview = usePendingRequestId()
  const editingDirty = Boolean(editing && editing.content !== editing.original)
  const guardUnsaved = useCallback(() => {
    if (editingDirty && !window.confirm('有未保存的修改，确定放弃并离开吗？')) return false
    setEditing(undefined)
    return true
  }, [editingDirty])
  const resetEditing = useCallback(() => {
    if (editingDirty && !window.confirm('有未保存的修改，确定撤销吗？')) return false
    setEditing(current => current ? { ...current, content: current.original } : current)
    return true
  }, [editingDirty])

  useEffect(() => {
    if (!editingDirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const programmaticLeave = (event: Event) => {
      if (!window.confirm('有未保存的修改，确定放弃并离开吗？')) event.preventDefault()
    }
    const linkClick = (event: MouseEvent) => {
      const link = (event.target as Element).closest?.('a[href]') as HTMLAnchorElement | null
      if (!link || link.target === '_blank' || event.ctrlKey || event.metaKey || link.href === window.location.href) return
      if (!window.confirm('有未保存的修改，确定放弃并离开吗？')) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    const historyIndex = window.history.state?.idx
    let restoringHistory = false
    const popState = (event: PopStateEvent) => {
      if (restoringHistory) { restoringHistory = false; event.stopImmediatePropagation(); return }
      const nextIndex = event.state?.idx
      if (typeof historyIndex !== 'number' || typeof nextIndex !== 'number' || nextIndex === historyIndex) return
      if (!window.confirm('有未保存的修改，确定放弃并离开吗？')) {
        event.stopImmediatePropagation()
        restoringHistory = true
        window.history.go(historyIndex - nextIndex)
      }
    }
    window.addEventListener('popstate', popState, true)
    window.addEventListener('beforeunload', warn)
    window.addEventListener(UNSAVED_NAVIGATION_EVENT, programmaticLeave)
    document.addEventListener('click', linkClick, true)
    return () => {
      window.removeEventListener('popstate', popState, true)
      window.removeEventListener('beforeunload', warn)
      window.removeEventListener(UNSAVED_NAVIGATION_EVENT, programmaticLeave)
      document.removeEventListener('click', linkClick, true)
    }
  }, [editingDirty])

  const overview = useQuery({
    queryKey: ['generationChain', requirementId, 'overview'],
    queryFn: () => generationChainApi.overview(requirementId),
    enabled,
    refetchInterval: query => {
      const chains = query.state.data?.chains ?? []
      return chains.some(chain => chain.active || chain.busy)
        ? 5_000
        : RUN_HISTORY_POLL_INTERVAL
    },
  })

  const detail = useQuery({
    queryKey: ['generationChain', requirementId, selected?.kind, 'detail'],
    queryFn: () => generationChainApi.chain(requirementId, selected!.kind),
    enabled: enabled && Boolean(selected),
    refetchInterval: query => {
      const chain = query.state.data
      return chain?.active || chain?.busy ? 5_000 : RUN_HISTORY_POLL_INTERVAL
    },
  })

  const chain: GenerationChain | undefined = detail.data
  const upstreamStages = useMemo(
    () => [...(chain?.stages ?? []), ...(overview.data?.chains ?? []).filter(item => item.kind !== chain?.kind).flatMap(item => item.stages)],
    [chain?.stages, chain?.kind, overview.data?.chains],
  )
  const stage: GenerationChainStage | undefined = useMemo(
    () => chain?.stages.find(item => item.stage === selected?.stage),
    [chain, selected?.stage],
  )

  const versionOptions = useMemo(() => {
    if (!stage) return []
    return [
      ...(stage.draft
        ? [{ key: 'draft', label: stage.draft.invalidated ? '已作废' : '待审核' }]
        : []),
      ...stage.versions.map(version => ({
        key: version.versionId,
        label: version.label,
      })),
    ]
  }, [stage])

  useEffect(() => {
    if (!stage || editing) return
    const valid =
      versionKey === 'draft'
        ? Boolean(stage.draft)
        : stage.versions.some(version => version.versionId === versionKey)
    if (!valid) {
      setVersionKey(
        stage.draft && !stage.draft.invalidated
          ? 'draft'
          : stage.latestVersion?.versionId ?? (stage.draft ? 'draft' : ''),
      )
    }
  }, [stage, versionKey, editing])

  // 待审核产物默认就是编辑态：打开草稿即建立工作副本，可视化与 JSON 共用同一份内容。
  const autoEditAttemptId = stage?.draft?.attemptId
  const autoEditContent = stage?.draft?.content
  const autoEditInvalidated = stage?.draft?.invalidated
  useEffect(() => {
    if (!autoEditAttemptId || !autoEditContent || autoEditInvalidated || versionKey !== 'draft') {
      setEditing(undefined)
      return
    }
    setEditing(current => {
      if (current?.attemptId === autoEditAttemptId) {
        // 其他人保存或轮询更新了草稿时，未修改的副本跟随最新内容；本地未保存的修改不覆盖。
        if (current.content === current.original && current.original !== autoEditContent) {
          return { ...current, content: autoEditContent, original: autoEditContent }
        }
        return current
      }
      return { content: autoEditContent, original: autoEditContent, attemptId: autoEditAttemptId }
    })
  }, [autoEditAttemptId, autoEditContent, autoEditInvalidated, versionKey, editing?.attemptId])

  const selectedVersion = useMemo(
    () =>
      versionKey && versionKey !== 'draft'
        ? stage?.versions.find(version => version.versionId === versionKey)
        : undefined,
    [stage?.versions, versionKey],
  )

  const openRevision = () => {
    if (!selected || !stage?.draft) return
    const key = `${requirementId}:${selected.kind}:${selected.stage}:${stage.draft.attemptId}`
    if (revisionDraftKey.current !== key) {
      const label = selected.kind === 'requirement_analysis'
        ? selected.stage === 'extracting_text' ? '材料提取结果' : '需求理解记录'
        : stage.label
      const template = buildRevisionTemplate(getRevisionQuestions(stage.draft.content), label, '答复')
      setRevisionTemplate(template)
      setRevisionInstruction(template)
      revisionAttachments.clearAttachments()
      revisionDraftKey.current = key
    }
    setRevisionOpen(true)
  }

  const versionDetail = useQuery({
    queryKey: [
      'generationChain',
      requirementId,
      selected?.kind,
      'version',
      selectedVersion?.versionId,
    ],
    queryFn: () =>
      generationChainApi.version(
        requirementId,
        selected!.kind,
        selectedVersion!.versionId,
      ),
    enabled: enabled && Boolean(selectedVersion),
  })

  const importableVersionId =
    selectedVersion && selected?.kind !== 'requirement_analysis'
      ? selectedVersion.versionId
      : ''
  const importOptions = useQuery({
    queryKey: [
      'generationChain',
      requirementId,
      selected?.kind,
      'importOptions',
      importableVersionId,
    ],
    queryFn: () =>
      generationChainApi.importOptions(
        requirementId,
        selected!.kind,
        importableVersionId,
      ),
    enabled: enabled && importOpen && Boolean(importableVersionId),
  })

  useEffect(() => {
    if (!importOpen) return
    const targets = importOptions.data?.targets ?? []
    if (targets.some(target => target.targetId === importTargetId)) return
    setImportTargetId(targets[0]?.targetId ?? '')
  }, [importOpen, importOptions.data?.targets, importTargetId])

  const comparisonId = useMemo(() => {
    if (!stage) return ''
    if (versionKey === 'draft') return stage.draft?.baseVersionId ?? ''
    const index = stage.versions.findIndex(version => version.versionId === versionKey)
    return index >= 0 ? stage.versions[index + 1]?.versionId ?? '' : ''
  }, [stage, versionKey])

  const comparison = useQuery({
    queryKey: [
      'generationChain',
      requirementId,
      selected?.kind,
      'version',
      comparisonId,
    ],
    queryFn: () =>
      generationChainApi.version(requirementId, selected!.kind, comparisonId),
    enabled: enabled && Boolean(comparisonId) && diffOpen,
  })

  const draftAttemptId = stage?.draft?.attemptId
  const draftUpstreamKey = JSON.stringify(stage?.draft?.upstreamVersions ?? {})
  const upstreamLatestSignature = useMemo(
    () =>
      (stage?.upstreamStages ?? [])
        .map(name => {
          const upstreamStage = upstreamStages.find(item => item.stage === name)
          return `${name}:${upstreamStage?.latestVersion?.versionId ?? ''}`
        })
        .join('|'),
    [upstreamStages, stage?.upstreamStages],
  )
  useEffect(() => {
    if (!upstreamLatestSignature) {
      setUpstream({})
      return
    }
    const draftUpstreams = JSON.parse(draftUpstreamKey) as Record<string, string>
    const next: Record<string, string> = {}
    for (const entry of upstreamLatestSignature.split('|').filter(Boolean)) {
      const separator = entry.indexOf(':')
      const upstreamStage = entry.slice(0, separator)
      const latestId = entry.slice(separator + 1)
      next[upstreamStage] = draftUpstreams[upstreamStage] ?? latestId
    }
    setUpstream(next)
  }, [draftAttemptId, draftUpstreamKey, upstreamLatestSignature, selected?.kind, selected?.stage])

  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: ['generationChain', requirementId] })
  }, [client, requirementId])

  const openStage = useCallback(
    (kind: GenerationChainKind, stageName: string) => {
      setSelected({ kind, stage: stageName })
      setMode('visual')
      setDiffOpen(false)
      setHistoryOpen(false)
      setRevisionOpen(false)
      setVersionKey('')
      setImportOpen(false)
      setImportConflicts([])
      setImportTargetId('')
    },
    [],
  )

  const closeStage = useCallback(() => {
    setSelected(undefined)
    setRevisionOpen(false)
    setImportOpen(false)
    setImportConflicts([])
    refresh()
  }, [refresh])

  // 关闭侧栏只需要退出阶段选择：清掉 selected 后详情查询自然停用，
  // 不再在后台按 30s/5s 轮询整条链的草稿正文；重新打开时会重新取一次。
  const clearStage = useCallback(() => {
    setSelected(undefined)
  }, [])

  const invalidate = () => {
    refresh()
    void client.invalidateQueries({
      queryKey: ['generationChain', requirementId, selected?.kind, 'detail'],
    })
  }

  const runStage = useMutation({
    mutationFn: async (inputs: { refreshInputs?: boolean; functionCaseIds?: string[] } | void) => {
      if (!selected) throw new Error('请选择阶段')
      const choice = selected.kind === 'api'
        ? await personalLlm.chooseRun(false, { label: '生成要求（选填）', placeholder: '例如：只处理登录接口，覆盖鉴权失败和参数边界' })
        : { connectionId: await personalLlm.choose({ alwaysConfirm: true }), instruction: '' }
      const params = {
        connectionId: choice.connectionId,
        ...(selected.kind === 'api' ? { instruction: choice.instruction.trim() } : {}),
        upstreamVersions: upstream,
        ...inputs,
      }
      const requestId = pendingRun.forInput(JSON.stringify({ requirementId, ...selected, ...params }))
      return generationChainApi.run(requirementId, selected.kind, selected.stage, { ...params, requestId })
    },
    onSuccess: () => {
      pendingRun.clear()
      invalidate()
      message.success('已开始生成')
    },
    onError: reason => {
      if (getErrorMessage(reason) !== '已取消操作') message.error(getErrorMessage(reason))
    },
  })

  const review = useMutation({
    mutationFn: async ({ action, continueAfter }: { action: ReviewAction; continueAfter?: boolean }) => {
      if (!selected) throw new Error('请选择阶段')
      const choice = action === 'approve' && continueAfter
        ? selected.kind === 'api'
          ? await personalLlm.chooseRun(false, { label: '生成要求（选填）', placeholder: '例如：只处理登录接口，覆盖鉴权失败和参数边界' })
          : { connectionId: await personalLlm.choose({ alwaysConfirm: true }), instruction: '' }
        : undefined
      const params = {
        action,
        ...(stage?.draft?.attemptId ? { expectedAttemptId: stage.draft.attemptId } : {}),
        continueAfter: Boolean(continueAfter),
        ...(choice?.connectionId ? { connectionId: choice.connectionId } : {}),
        ...(choice && selected.kind === 'api' ? { instruction: choice.instruction.trim() } : {}),
      }
      const requestId = continueAfter
        ? pendingReview.forInput(JSON.stringify({ requirementId, ...selected, ...params }))
        : undefined
      return generationChainApi.review(requirementId, selected.kind, selected.stage, { ...params, requestId })
    },
    onSuccess: (result, variables) => {
      pendingReview.clear()
      invalidate()
      if (result.continuationError) {
        message.warning(`已审核通过，下一阶段未启动：${result.continuationError}`)
        return
      }
      message.success(
        variables.action === 'reject'
          ? '已删除候选'
          : variables.continueAfter
            ? '已通过并继续下一阶段'
            : '已审核通过并生成版本',
      )
    },
    onError: reason => {
      if (getErrorMessage(reason) !== '已取消操作') message.error(getErrorMessage(reason))
    },
  })

  const saveDraft = useMutation({
    mutationFn: async () => {
      if (!selected || !editing) throw new Error('当前没有可保存的产物')
      return generationChainApi.saveDraft(requirementId, selected.kind, selected.stage, {
        expectedAttemptId: editing.attemptId,
        content: editing.content,
      })
    },
    onSuccess: result => {
      client.setQueryData(['generationChain', requirementId, selected?.kind, 'detail'], result)
      setEditing(undefined)
      invalidate()
      message.success('已保存，等待审核')
    },
    onError: reason => message.error(getErrorMessage(reason)),
  })

  const revise = useMutation({
    mutationFn: async (connectionId: string) => {
      if (!selected) throw new Error('请选择阶段')
      if (!revisionInstruction.trim()) throw new Error('请输入优化指令')
      if (revisionTemplate && revisionInstruction.trim() === revisionTemplate.trim()) {
        throw new Error('请补充已确认的信息，或填写其他优化要求')
      }
      const params = {
        connectionId, instruction: revisionInstruction.trim(),
        ...(revisionAttachments.attachments.length ? {
          attachmentFileIds: revisionAttachments.attachments.map(item => item.fileId),
        } : {}),
      }
      const requestId = pendingRevision.forInput(JSON.stringify({ requirementId, ...selected, ...params }))
      return generationChainApi.revise(
        requirementId,
        selected.kind,
        selected.stage,
        { ...params, requestId },
      )
    },
    onSuccess: () => {
      pendingRevision.clear()
      invalidate()
      setRevisionOpen(false)
      setRevisionInstruction('')
      setRevisionTemplate('')
      revisionAttachments.clearAttachments()
      revisionDraftKey.current = ''
      message.success('已提交继续优化')
    },
    onError: reason => { message.error(getErrorMessage(reason)) },
  })

  const deleteVersion = useMutation({
    mutationFn: async (versionId: string) => {
      if (!selected) throw new Error('请选择阶段')
      return generationChainApi.deleteVersion(requirementId, selected.kind, versionId)
    },
    onSuccess: (result, versionId) => {
      if (versionKey === versionId) setVersionKey('')
      invalidate()
      message.success(
        result.invalidatedDraftCount
          ? `版本已删除，${result.invalidatedDraftCount} 个依赖的待审核产物已作废`
          : '版本已删除',
      )
    },
    onError: reason => message.error(getErrorMessage(reason)),
  })

  const openImport = useCallback(() => {
    if (!importableVersionId) return
    setImportOpen(true)
    setImportTargetId('')
    setImportConflicts([])
  }, [importableVersionId])

  const closeImport = useCallback(() => {
    setImportOpen(false)
    setImportTargetId('')
    setImportConflicts([])
  }, [])

  const importVersion = useMutation({
    mutationFn: async (confirmOverwrite: boolean) => {
      if (!selected || !importableVersionId) throw new Error('请选择已通过的叶子版本')
      return generationChainApi.importVersion(
        requirementId,
        selected.kind,
        importableVersionId,
        {
          ...(importTargetId ? { targetId: importTargetId } : {}),
          confirmOverwrite,
        },
      )
    },
    onSuccess: result => {
      invalidate()
      void client.invalidateQueries({
        queryKey: [
          'generationChain',
          requirementId,
          selected?.kind,
          'importOptions',
          importableVersionId,
        ],
      })
      if (result.requiresConfirmation) {
        setImportConflicts(result.conflicts)
        return
      }
      if (result.chain) {
        client.setQueryData(
          ['generationChain', requirementId, selected?.kind, 'detail'],
          result.chain,
        )
      }
      const targetKeys =
        selected?.kind === 'function'
          ? ['functionTestSuites', 'functionTestCases']
          : selected?.kind === 'api'
            ? ['apiCollections']
            : ['uiTestSuites']
      for (const key of targetKeys) {
        void client.invalidateQueries({ queryKey: [key] })
      }
      void client.invalidateQueries({ queryKey: ['sprintDailyMetrics'] })
      void client.invalidateQueries({ queryKey: ['sprintDailyMetricsByDate'] })
      closeImport()
      message.success(`已导入 ${result.changedCaseCount} 条正式用例`)
    },
    onError: reason => message.error(getErrorMessage(reason)),
  })

  const displayedContent =
    versionKey === 'draft'
      ? stage?.draft?.content ?? ''
      : versionDetail.data?.content ?? ''

  const workingContent = editing?.content ?? displayedContent

  const comparisonContent =
    versionKey === 'draft'
      ? comparison.data?.content ?? ''
      : comparison.data?.content ?? ''

  const operationPending =
    runStage.isPending ||
    review.isPending ||
    saveDraft.isPending ||
    revise.isPending ||
    deleteVersion.isPending ||
    importVersion.isPending
  const busy = operationPending || stage?.state === 'running'

  return {
    overview,
    upstreamStages,
    detail,
    chain,
    stage,
    selected,
    selectedVersion,
    versionDetail,
    versionOptions,
    versionKey,
    setVersionKey: (value: string) => { if (value === versionKey || guardUnsaved()) setVersionKey(value) },
    displayedContent,
    workingContent,
    comparisonContent,
    comparisonId,
    diffOpen,
    setDiffOpen,
    mode,
    setMode,
    historyOpen,
    setHistoryOpen,
    revisionOpen,
    openRevision,
    revisionAttachments,
    setRevisionOpen,
    revisionInstruction,
    setRevisionInstruction,
    upstream,
    setUpstream,
    filter,
    setFilter,
    openStage,
    closeStage,
    clearStage,
    refresh,
    runStage,
    review,
    editing,
    editingDirty,
    setEditingContent: (content: string) => setEditing(current => current
      ? { ...current, content }
      : stage?.draft
        ? { content, original: stage.draft.content, attemptId: stage.draft.attemptId }
        : current),
    resetEditing,
    guardUnsaved,
    saveDraft,
    revise,
    deleteVersion,
    importOpen,
    importTargetId,
    setImportTargetId,
    importConflicts,
    importOptions,
    importVersion,
    importableVersionId,
    openImport,
    closeImport,
    busy,
    operationPending,
    personalLlm,
  }
}

export type GenerationChainWorkspace = ReturnType<typeof useRequirementGenerationChain>
export type { GenerationChainVersionDetail }
