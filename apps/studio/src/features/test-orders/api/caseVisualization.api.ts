import { request } from '@/shared/api/request'
import type { VisualizationBatch, VisualizationReceipt, VisualizationState } from '../visualizationTypes'

export const caseVisualizationApi = {
  get: (orderId: string, entryId: string) => request<VisualizationState>(`/v1/test-orders/${orderId}/entries/${entryId}/visualization`),
  generate: (orderId: string, entryId: string, connectionId: string, requestId: string, mode: 'generate' | 'regenerate') => request<VisualizationReceipt>(`/v1/test-orders/${orderId}/entries/${entryId}/visualization/runs`, { method: 'POST', body: JSON.stringify({ connectionId, requestId, mode }) }),
  batch: (orderId: string, entryIds: string[], connectionId: string, requestId: string) => request<VisualizationBatch>(`/v1/test-orders/${orderId}/visualization-batches`, { method: 'POST', body: JSON.stringify({ entryIds, connectionId, requestId }) }),
  getBatch: (orderId: string, batchId: string) => request<VisualizationBatch>(`/v1/test-orders/${orderId}/visualization-batches/${batchId}`),
}

export const isVisualizationRunning = (status?: string) => ['pending', 'claimed', 'running'].includes(status ?? '')
export function visualizationStatus(status?: string, artifactStatus?: string | null): string {
  const labels: Record<string, string> = { pending: '排队中', claimed: '准备生成', running: '生成中', failed: '生成失败', error: '生成失败', canceled: '已取消', ready: '已生成', partial: '部分内容未图解', unsupported: '暂不适合图解', success: '已完成', skipped_available: '已有图解，已跳过', existing_active: '正在生成，已复用', rejected: '未提交', queued: '已提交' }
  return labels[artifactStatus || status || ''] ?? '尚未生成'
}
