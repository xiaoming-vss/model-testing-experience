export function footerRange(total: number, currentPage: number, currentPageSize: number) {
  if (total === 0) return '显示第 0 条 - 第 0 条，共 0 条'
  const start = (currentPage - 1) * currentPageSize + 1
  const end = Math.min(currentPage * currentPageSize, total)
  return `显示第 ${start} 条 - 第 ${end} 条，共 ${total} 条`
}
