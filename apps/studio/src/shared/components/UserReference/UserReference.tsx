import { Tag } from 'antd'

export const DELETED_ACCOUNT_LABEL = '已删除账户'

export function DeletedAccountLabel() {
  return <Tag bordered={false}>{DELETED_ACCOUNT_LABEL}</Tag>
}

export function UserDisplayName({ name }: { name: string }) {
  return name === DELETED_ACCOUNT_LABEL ? <DeletedAccountLabel /> : <>{name}</>
}
