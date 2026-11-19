/** 下拉选项：只包含识别与展示字段，接口不返回 documentContent。 */
export type RequirementOption = {
  requirementId: string
  sprintId: string
  sprintName: string
  name: string
  documentFilename?: string
  createdAt?: string
}
