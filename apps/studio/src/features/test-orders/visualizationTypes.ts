export type VisualizationMode = 'text' | 'visual'
export type Source = { id: string; field: 'precondition' | 'action' | 'expected'; index: number }
export type Constraint = { operator: 'eq' | 'gt' | 'gte' | 'lt' | 'lte'; value: number; unit: string; sourceIds: string[] }
export type Entity = { id: string; kind: string; label: string; sourceIds: string[]; durationConstraint?: Constraint; countConstraint?: Constraint; range?: { start: number | null; end: number | null; unit: string; startInclusive: boolean | null; endInclusive: boolean | null; timeBase: string | null; sourceIds: string[] } }
export type Relation = { id: string; kind: string; from: string; to: string; polarity: 'positive' | 'negative'; sourceIds: string[]; condition?: { text: string; sourceIds: string[] } }
type VisualBase = { id: string; title: string; sourceIds: string[]; entityIds: string[]; relationIds: string[]; assertionIds: string[]; isSchematic: boolean; notes: { kind: 'action_check'; text: string; sourceIds: string[] }[] }
export type Visual = VisualBase & (
  | { kind: 'options'; data: { ownerEntityId: string; optionEntityIds: string[]; completeness: 'exhaustive' | 'examples' | 'unknown'; availability: 'allowed' | 'forbidden' | 'unknown'; sourceIds: string[] } }
  | { kind: 'interval'; data: { orderedSegments: { entityId: string; role: 'keep' | 'remove' | 'unknown'; sourceIds: string[] }[]; orderSourceIds: string[]; distinctOutputEntityIds: string[]; distinctOutputSourceIds: string[] } }
  | { kind: 'state'; data: { actionEntityId: string; beforeEntityId: string | null; afterEntityId: string | null; change: 'changed' | 'unchanged' | 'unknown'; sourceIds: string[] } }
  | { kind: 'quantity'; data: { sourceEntityIds: string[]; outputEntityIds: string[]; ownership: 'distinct' | 'shared' | 'unknown'; totalConstraint: Constraint | null; sourceIds: string[] } }
)
export type Visualization = {
  schemaVersion: '1.0'; executionEntryId: string; status: 'ready' | 'partial' | 'unsupported'
  summary: { text: string | null; sourceIds: string[] }; sources: Source[]; entities: Entity[]; relations: Relation[]
  assertions: { id: string; text: string; sourceIds: string[]; entityIds: string[] }[]
  visuals: Visual[]; limitations: { reason: string; sourceIds: string[] }[]
}
export type VisualizationRun = { runId: string | null; status: string; artifactStatus: Visualization['status'] | null; errorMessage: string | null }
export type VisualizationState = {
  executionEntryId: string; snapshotHash: string | null; unavailableReason: string | null
  effectiveArtifact: { artifactId: string; runId: string | null; schemaVersion: string; status: 'ready' | 'partial'; content: Visualization | null } | null
  latestRun: VisualizationRun | null
}
export type VisualizationReceipt = { entryId: string; disposition: 'queued' | 'existing_active' | 'skipped_available' | 'rejected'; runId?: string | null; errorMessage?: string | null; run?: VisualizationRun | null }
export type VisualizationBatch = { batchId: string; items: VisualizationReceipt[]; total: number; counts: Record<string, number> }
