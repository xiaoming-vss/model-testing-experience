export type MaterialBlock = {
  id: string
  sourceId: string
  kind: string
  locator: string
  content: Record<string, unknown>
}

export type MaterialItem = {
  text: string
  status: string
  materialBlockIds: string[]
}

export type MaterialSection = {
  title: string
  items: MaterialItem[]
}

export type MaterialFeature = {
  id: string
  name: string
  sections: MaterialSection[]
}

export type MaterialQuestion = {
  id: string
  question: string
  reason: string
  materialBlockIds: string[]
  functionIds: string[]
}

export type MaterialSource = {
  id: string
  name: string
  location: string | null
}

export type RequirementMaterial = {
  artifactType: string
  title: string
  sources: MaterialSource[]
  materialBlocks: MaterialBlock[]
  functions: MaterialFeature[]
  questions: MaterialQuestion[]
}
