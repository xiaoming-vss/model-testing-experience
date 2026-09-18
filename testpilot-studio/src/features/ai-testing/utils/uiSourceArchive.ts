const MAX_SOURCE_ARCHIVE_BYTES = 100 * 1024 * 1024

export function validateUiSourceArchive(file?: File) {
  if (!file) return '请选择源码 ZIP'
  if (!file.name.toLowerCase().endsWith('.zip')) return '只支持 .zip 源码包'
  if (file.size > MAX_SOURCE_ARCHIVE_BYTES) return '源码包不能超过 100 MiB'
  return undefined
}
