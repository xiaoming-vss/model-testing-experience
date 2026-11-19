import { AutoComplete, Input, Modal, Radio, Tag } from 'antd'
import type { InterfaceDetailPageModel } from '../hooks/useInterfaceDetailPage'
import styles from '../styles/interface-library.module.css'
import detailStyles from '../styles/interface-detail.module.css'

const interfaceScopes = `${styles.scope} ${detailStyles.scope}`

export function InterfaceGroupModals({ page }: { page: InterfaceDetailPageModel }) {
  const {
    createGroupRepository,
    setCreateGroupRepository,
    createGroupName,
    setCreateGroupName,
    submitCreateGroup,
    createGroupMutation,
    groupRenameTarget,
    setGroupRenameTarget,
    groupRenameValue,
    setGroupRenameValue,
    submitRenameGroup,
    renameGroupMutation,
    moveTarget,
    setMoveTarget,
    moveMode,
    setMoveMode,
    moveGroupName,
    setMoveGroupName,
    submitMoveInterface,
    moveMutation,
  } = page

  return (
    <>
      <Modal
        rootClassName={interfaceScopes}
        open={Boolean(createGroupRepository)}
        title="新建分组"
        okText="创建"
        cancelText="取消"
        confirmLoading={createGroupMutation.isPending}
        destroyOnHidden
        onOk={submitCreateGroup}
        onCancel={() => setCreateGroupRepository(null)}
      >
        <div className="if-group-modal flex flex-col gap-3">
          <div className="if-group-modal-label flex items-center gap-2 text-[12px] text-[var(--srf-text-secondary)]">
            <span>软件仓库</span>
            <Tag>{createGroupRepository?.name}</Tag>
          </div>
          <Input
            aria-label="分组名称"
            value={createGroupName}
            maxLength={50}
            showCount
            placeholder="输入分组名称"
            onChange={event => setCreateGroupName(event.target.value)}
            onPressEnter={submitCreateGroup}
          />
          <p className="if-group-modal-hint m-0 text-[12px] leading-[1.6] text-[var(--srf-text-muted)]">
            分组会保存在软件仓库中，即使暂时没有接口也会保留；可在接口的「更多操作」中移动接口进来。
          </p>
        </div>
      </Modal>
      <Modal
        rootClassName={interfaceScopes}
        open={Boolean(groupRenameTarget)}
        title="重命名分组"
        okText="保存"
        cancelText="取消"
        confirmLoading={renameGroupMutation.isPending}
        destroyOnHidden
        onOk={submitRenameGroup}
        onCancel={() => setGroupRenameTarget(null)}
      >
        <div className="if-group-modal">
          <div className="if-group-modal-label">
            <span>当前分组</span>
            <Tag>{groupRenameTarget?.group.tag}</Tag>
          </div>
          <Input
            aria-label="新分组名称"
            value={groupRenameValue}
            maxLength={50}
            showCount
            placeholder="输入新的分组名称"
            onChange={event => setGroupRenameValue(event.target.value)}
            onPressEnter={submitRenameGroup}
          />
          <p className="if-group-modal-hint">
            将修改该分组下接口的首个标签；若目标分组已存在，操作会被拒绝，不会自动合并。
          </p>
        </div>
      </Modal>
      <Modal
        rootClassName={interfaceScopes}
        open={Boolean(moveTarget)}
        title="移动到分组"
        okText="移动"
        cancelText="取消"
        confirmLoading={moveMutation.isPending}
        destroyOnHidden
        onOk={submitMoveInterface}
        onCancel={() => setMoveTarget(null)}
      >
        <div className="if-group-modal">
          <div className="if-group-modal-label">
            <span>接口</span>
            <span className="if-group-modal-interface min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-medium text-[var(--srf-text)]">
              {moveTarget?.item.name || moveTarget?.item.path}
            </span>
          </div>
          <Radio.Group
            value={moveMode}
            onChange={event => setMoveMode(event.target.value)}
          >
            <Radio value="group">移动到分组</Radio>
            <Radio value="clear">清除全部标签（归入「未分类」）</Radio>
          </Radio.Group>
          {moveMode === 'group' ? (
            <AutoComplete
              className="if-group-move-select w-full"
              aria-label="目标分组"
              value={moveGroupName}
              options={(moveTarget?.groups ?? []).map(name => ({
                value: name,
                label: name,
              }))}
              placeholder="选择已有分组，或输入新分组名称"
              onChange={value => setMoveGroupName(value)}
            />
          ) : null}
          <p className="if-group-modal-hint">
            移动到已有或新分组会将该标签置顶；清除标签后接口归入「未分类」，次要标签也会被清除。
          </p>
        </div>
      </Modal>
    </>
  )
}
