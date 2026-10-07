import { Alert, Button, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { goBackOrFallback } from '@/shared/utils/backNavigation'
import { RequirementDocumentPreviewModal } from '@/features/requirements/components/RequirementDocumentPreviewModal'
import { requirementsApi } from '@/features/requirements/api/requirements.api'
import { getErrorMessage } from '@/utils/format'

export function RequirementPreviewPage() {
  const { requirementId = '' } = useParams()
  const navigate = useNavigate()
  const query = useQuery({ queryKey: ['requirement', requirementId],
    queryFn: () => requirementsApi.getRequirement(requirementId), enabled: Boolean(requirementId) })
  const back = () => goBackOrFallback(navigate, '/projects?board=requirements')
  if (query.isPending) return <Spin />
  if (query.error) return <Alert type="error" title={getErrorMessage(query.error)} action={<Button onClick={back}>返回</Button>} />
  const requirement = query.data!
  return <RequirementDocumentPreviewModal open onClose={back} requirementId={requirementId}
    requirementName={requirement.name} documentType={requirement.documentType}
    documentContent={requirement.documentContent} documentFilename={requirement.documentFilename}
    documentDownloadUrl={requirement.documentDownloadUrl} />
}
