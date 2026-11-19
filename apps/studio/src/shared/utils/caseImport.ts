export type CaseImportMode = 'upload' | 'editor'

export function isYamlFileName(fileName: string) {
  return /\.(yaml|yml)$/i.test(fileName.trim())
}
