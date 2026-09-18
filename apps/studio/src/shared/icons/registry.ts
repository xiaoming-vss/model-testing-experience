import testing from './assets/nav-testing.svg?url'
import services from './assets/nav-services.svg?url'
import testDesign from './assets/nav-testDesign.svg?url'
import projects from './assets/nav-projects.svg?url'
import codeRisk from './assets/codeRisk.svg?url'
import analysis from './assets/analysis.svg?url'
import skills from './assets/skills.svg?url'
import tasks from './assets/tasks.svg?url'
import ui from './assets/ui.svg?url'
import api from './assets/api.svg?url'
import functional from './assets/functional.svg?url'
import caseLibrary from './assets/caseLibrary.svg?url'
import requirement from './assets/requirement.svg?url'
import sprint from './assets/sprint.svg?url'
import llm from './assets/llm-chat.svg?url'
import zentao from './assets/zentao.ico?url'
import gitlab from './assets/gitlab.png?url'

export const iconRegistry = {
  testing: { src: testing, label: '测试' },
  services: { src: services, label: '基础服务' },
  testDesign: { src: testDesign, label: '测试设计' },
  projects: { src: projects, label: '项目总览' },
  codeRisk: { src: codeRisk, label: '代码风险分析' },
  analysis: { src: analysis, label: '需求分析' },
  skills: { src: skills, label: 'Skill库' },
  tasks: { src: tasks, label: '任务' },
  ui: { src: ui, label: 'UI测试' },
  api: { src: api, label: 'API测试' },
  functional: { src: functional, label: '功能测试' },
  caseLibrary: { src: caseLibrary, label: '用例库' },
  requirement: { src: requirement, label: '需求' },
  sprint: { src: sprint, label: '迭代' },
  llm: { src: llm, label: 'LLM 模型' },
  zentao: { src: zentao, label: '禅道' },
  gitlab: { src: gitlab, label: 'GitLab' },
} as const

export type AppIconName = keyof typeof iconRegistry
