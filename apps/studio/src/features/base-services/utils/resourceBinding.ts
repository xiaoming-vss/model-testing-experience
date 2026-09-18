import type { ResourceBinding } from '@/features/base-services/types'

export function getBindingId(binding: ResourceBinding) {
  return binding.bindingId ?? binding.binding_id ?? ''
}

export function getBindingConnectionId(binding: ResourceBinding) {
  return binding.connectionId ?? binding.connection_id ?? ''
}

export function getBindingRemoteResourceId(binding: ResourceBinding) {
  return binding.remoteResourceId ?? binding.remote_resource_id ?? ''
}

export function getBindingRemoteName(binding: ResourceBinding) {
  return binding.remoteNameSnapshot ?? binding.remote_name_snapshot ?? getBindingRemoteResourceId(binding)
}

export function getBindingRemoteParentId(binding: ResourceBinding) {
  return binding.remoteParentId ?? binding.remote_parent_id ?? ''
}

export function isGitlabGroupBinding(binding: ResourceBinding) {
  return binding.provider === 'gitlab' && (binding.remoteResourceType ?? binding.remote_resource_type ?? '') === 'group'
}

export function isGitlabRepositoryBinding(binding: ResourceBinding) {
  return binding.provider === 'gitlab' && (binding.remoteResourceType ?? binding.remote_resource_type ?? '') === 'repository'
}
