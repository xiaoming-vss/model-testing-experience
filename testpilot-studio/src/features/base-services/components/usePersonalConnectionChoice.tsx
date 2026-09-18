import { useEffect, useRef, useState } from 'react'
import { Alert, Modal, Select } from 'antd'
import { api, listItems } from '@/services/api'
import { normalizeInstanceUrl } from '../utils/personalConnections'

type Choice = { connectionId: string; name: string; baseUrl: string; status: string }
export function usePersonalConnectionChoice(provider: 'gitlab' | 'zentao') {
  const [choices, setChoices] = useState<Choice[] | null>(null)
  const [selected, setSelected] = useState<string>()
  const [instance, setInstance] = useState('')
  const pending = useRef<{ resolve: (id: string) => void; reject: (e: Error) => void } | null>(null)
  function finish(id?: string) {
    if (id) pending.current?.resolve(id)
    else pending.current?.reject(new Error('已取消操作'))
    pending.current = null
    setChoices(null)
    setSelected(undefined)
  }
  useEffect(() => () => { pending.current?.reject(new Error('页面已关闭')); pending.current = null }, [])
  async function choose(projectId: string, instanceUrl?: string) {
    const rows = listItems(await (provider === 'gitlab' ? api.getGitlabConnections(projectId) : api.getZentaoConnections(projectId)))
      .filter(c => c.status === 'active' && (!instanceUrl || normalizeInstanceUrl(c.baseUrl) === normalizeInstanceUrl(instanceUrl)))
    if (rows.length === 1) return rows[0].connectionId
    pending.current?.reject(new Error('已取消上一次操作'))
    setInstance(instanceUrl ?? '')
    setSelected(undefined)
    setChoices(rows)
    return new Promise<string>((resolve, reject) => { pending.current = { resolve, reject } })
  }
  async function forRequirement(projectId: string, requirementId: string) {
    const bindings = listItems(await api.getGitlabRequirementBindings(requirementId)).filter(b => b.provider === 'gitlab' && b.status === 'active')
    const result: Record<string, string> = {}
    for (const url of new Set(bindings.map(b => b.instanceUrl))) {
      if (!url) throw new Error('绑定缺少实例信息，请由项目所有者重新绑定')
      result[url] = await choose(projectId, url)
    }
    return result
  }
  async function forZentaoRequirement(projectId: string, requirementId: string) {
    const binding = listItems(await api.getRequirementBindings(requirementId)).find(b => b.provider === 'zentao' && b.status === 'active')
    if (!binding?.instanceUrl) throw new Error('需求未绑定禅道实例，请先由项目所有者绑定')
    return choose(projectId, binding.instanceUrl)
  }
  const dialog = <Modal title={`选择本人 ${provider === 'gitlab' ? 'GitLab' : '禅道'} 授权${instance ? ` · ${instance}` : ''}`} open={choices !== null} onCancel={() => finish()} onOk={() => finish(selected)} okButtonProps={{ disabled: !choices?.some(c => c.connectionId === selected) }}>
    {choices?.length ? <Select style={{ width: '100%' }} aria-label="选择本人授权" placeholder="请选择本次操作使用的连接" value={selected} onChange={setSelected} options={choices.map(c => ({ value: c.connectionId, label: `${c.name} · ${c.baseUrl}` }))} /> : <Alert type="info" showIcon title="没有可用的本人授权" description="请先关闭此窗口，前往基础服务配置对应实例的个人连接。" />}
  </Modal>
  return { choose, forRequirement, forZentaoRequirement, dialog }
}
