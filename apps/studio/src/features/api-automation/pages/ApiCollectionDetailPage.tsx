import { ProjectAccessScope } from '@/domain/projects/components/ProjectAccessScope'
import { ApiCollectionOverlays } from '../components/ApiCollectionOverlays'
import { ApiCollectionWorkspace } from '../components/ApiCollectionWorkspace'
import { useApiCollectionDetailPage } from '../hooks/useApiCollectionDetailPage'
import shellStyles from '../styles/api-detail-shell.module.css'
import rulesStyles from '../styles/api-detail-rules.module.css'

export function ApiCollectionDetailPage() {
  const page = useApiCollectionDetailPage()

  return (<ProjectAccessScope projectId={page.projectId ?? ''}>{(
    <div className={`workbench-page api-collection-detail-page api-collection-workbench-page tp-surface [--font-mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] ${shellStyles.scope} ${rulesStyles.scope}`}>
      <ApiCollectionWorkspace page={page} />
      <ApiCollectionOverlays page={page} />
    </div>
  )}</ProjectAccessScope>)
}
