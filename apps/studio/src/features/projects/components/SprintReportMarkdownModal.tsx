import { Alert, Button, Empty, Modal, Space, Spin } from 'antd'
import type { ReactNode } from 'react'
import { ActionButton } from '@/shared/components/ActionButton'
import { getErrorMessage } from '@/utils/format'
import type { TestReportGenerateRun } from '@/services/api'
import { normalizeRunStatus } from '@/domain/runs/status'
import {
  getRunId,
  getRunReportMarkdown,
} from '../utils/sprintReport'
import sprintOverviewStyles from '../styles/sprint-overview.module.css'

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean)
  return parts.map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${part}-${index}`}>{part}</span>
  })
}

function parseMarkdownTable(lines: string[]) {
  if (lines.length < 2 || !/^\s*\|?[\s:-]+\|[\s|:-]*$/.test(lines[1])) return null

  const toCells = (line: string) =>
    line
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim())

  const headers = toCells(lines[0])
  const rows = lines.slice(2).map(toCells)
  return { headers, rows }
}

function renderMarkdownBlocks(markdown: string) {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.trim().startsWith('```')) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      index += 1
      blocks.push(
        <pre key={`code-${index}`}>
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      const content = renderInlineMarkdown(heading[2])
      if (level === 1) blocks.push(<h1 key={`heading-${index}`}>{content}</h1>)
      else if (level === 2) blocks.push(<h2 key={`heading-${index}`}>{content}</h2>)
      else if (level === 3) blocks.push(<h3 key={`heading-${index}`}>{content}</h3>)
      else blocks.push(<h4 key={`heading-${index}`}>{content}</h4>)
      index += 1
      continue
    }

    if (line.includes('|') && index + 1 < lines.length && lines[index + 1].includes('|')) {
      const tableLines: string[] = []
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        tableLines.push(lines[index])
        index += 1
      }
      const table = parseMarkdownTable(tableLines)
      if (table) {
        blocks.push(
          <div className="sprint-report-markdown-table-wrap my-3 overflow-auto rounded-[8px] border border-[var(--app-document-table-border)]" key={`table-${index}`}>
            <table>
              <thead>
                <tr>
                  {table.headers.map((header, headerIndex) => (
                    <th key={`${header}-${headerIndex}`}>{renderInlineMarkdown(header)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, rowIndex) => (
                  <tr key={`row-${rowIndex}`}>
                    {row.map((cell, cellIndex) => (
                      <td key={`${cell}-${cellIndex}`}>{renderInlineMarkdown(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        )
        continue
      }
      blocks.push(<p key={`paragraph-${index}`}>{renderInlineMarkdown(tableLines.join(' '))}</p>)
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ''))
        index += 1
      }
      blocks.push(
        <ul key={`list-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>,
      )
      continue
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ''))
        index += 1
      }
      blocks.push(
        <ol key={`ordered-list-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ol>,
      )
      continue
    }

    if (/^\s*>\s+/.test(line)) {
      const quotes: string[] = []
      while (index < lines.length && /^\s*>\s+/.test(lines[index])) {
        quotes.push(lines[index].replace(/^\s*>\s+/, ''))
        index += 1
      }
      blocks.push(<blockquote key={`quote-${index}`}>{renderInlineMarkdown(quotes.join(' '))}</blockquote>)
      continue
    }

    const paragraph: string[] = []
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,4})\s+/.test(lines[index]) &&
      !lines[index].trim().startsWith('```') &&
      !/^\s*[-*]\s+/.test(lines[index]) &&
      !/^\s*\d+\.\s+/.test(lines[index]) &&
      !/^\s*>\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index])
      index += 1
    }
    blocks.push(<p key={`paragraph-${index}`}>{renderInlineMarkdown(paragraph.join(' '))}</p>)
  }

  return blocks
}

export function TestReportMarkdownModal({
  open,
  run,
  loading,
  error,
  downloading,
  onClose,
  onDownloadPdf,
}: {
  open: boolean
  run?: TestReportGenerateRun
  loading?: boolean
  error?: unknown
  downloading?: boolean
  onClose: () => void
  onDownloadPdf: (run: TestReportGenerateRun) => void
}) {
  const markdown = getRunReportMarkdown(run)
  const canDownload = Boolean(run && normalizeRunStatus(run.status) === 'success' && getRunId(run) && markdown)

  return (
    <Modal
      title="测试报告"
      open={open}
      onCancel={onClose}
      width={960}
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          <ActionButton
            type="primary"
            operation="download"
            disabled={!canDownload}
            loading={downloading}
            onClick={() => {
              if (run) onDownloadPdf(run)
            }}
          >
            导出 PDF
          </ActionButton>
        </Space>
      }
      destroyOnHidden={false}
      className={`sprint-report-markdown-modal ${sprintOverviewStyles.root}`}
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} style={{ marginBottom: 16 }} /> : null}
      {loading ? (
        <div className="sprint-report-markdown-state flex min-h-[220px] items-center justify-center">
          <Spin />
        </div>
      ) : markdown ? (
        <article className="sprint-report-markdown text-[14px] leading-[1.72] text-[var(--app-document-text)] [&_blockquote]:my-3 [&_blockquote]:border-l-[3px] [&_blockquote]:border-[var(--app-accent)] [&_blockquote]:bg-[var(--app-document-quote-bg)] [&_blockquote]:px-3.5 [&_blockquote]:py-2.5 [&_blockquote]:text-[var(--app-document-quote-text)] [&_code]:rounded-[5px] [&_code]:bg-[var(--app-document-code-bg)] [&_code]:px-[5px] [&_code]:py-0.5 [&_code]:text-[12px] [&_code]:text-[var(--app-document-code-text)] [&_h1]:mb-2.5 [&_h1]:mt-5 [&_h1]:text-[24px] [&_h1]:font-[750] [&_h1]:text-[var(--app-document-heading)] [&_h2]:mb-2.5 [&_h2]:mt-5 [&_h2]:text-[20px] [&_h2]:font-[750] [&_h2]:text-[var(--app-document-heading)] [&_h3]:mb-2.5 [&_h3]:mt-5 [&_h3]:text-[17px] [&_h3]:font-[750] [&_h3]:text-[var(--app-document-heading)] [&_h4]:mb-2.5 [&_h4]:mt-5 [&_h4]:text-[15px] [&_h4]:font-[750] [&_h4]:text-[var(--app-document-heading)] [&_li]:my-1 [&_ol]:my-2 [&_ol]:mb-3 [&_ol]:pl-6 [&_p]:my-2 [&_pre]:my-3 [&_pre]:overflow-auto [&_pre]:rounded-[8px] [&_pre]:bg-[var(--app-document-code-block-bg)] [&_pre]:p-3 [&_pre_code]:whitespace-pre [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-[var(--app-document-code-block-text)] [&_table]:w-full [&_table]:min-w-[560px] [&_table]:border-collapse [&_td]:border-b [&_td]:border-[var(--app-frame-divider)] [&_td]:px-3 [&_td]:py-2.5 [&_td]:text-left [&_td]:align-top [&_th]:border-b [&_th]:border-[var(--app-frame-divider)] [&_th]:bg-[var(--app-document-table-heading-bg)] [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-left [&_th]:align-top [&_th]:font-bold [&_th]:text-[var(--app-text-strong)] [&_ul]:my-2 [&_ul]:mb-3 [&_ul]:pl-6">{renderMarkdownBlocks(markdown)}</article>
      ) : (
        <Empty description="暂无可查看的报告内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </Modal>
  )
}
