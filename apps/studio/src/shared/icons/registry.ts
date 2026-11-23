import navBug from './assets/nav-bug.svg?url'
import skills from './assets/skills.svg?url'
import sprint from './assets/sprint.svg?url'
import llm from './assets/llm-chat.svg?url'
import zentao from './assets/zentao.ico?url'
import gitlab from './assets/gitlab.png?url'

export const iconRegistry = {
  navBug: { src: navBug, label: 'Bug列表' },
  skills: { src: skills, label: 'Skill库' },
  sprint: { src: sprint, label: '迭代' },
  llm: { src: llm, label: 'LLM 模型' },
  zentao: { src: zentao, label: '禅道' },
  gitlab: { src: gitlab, label: 'GitLab' },
} as const

export type AppIconName = keyof typeof iconRegistry
