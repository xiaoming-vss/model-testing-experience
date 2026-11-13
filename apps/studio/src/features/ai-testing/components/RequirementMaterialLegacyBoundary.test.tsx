import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import extraction from '@/domain/requirements/fixtures/document-extraction.example.json'
import { RequirementMaterialComparison } from './RequirementMaterialComparison'

it('旧材料产物不进入旧事实列表，并提示重新生成', () => {
  render(<RequirementMaterialComparison content={extraction} />)
  expect(screen.getByText(/旧版材料产物/)).toBeVisible()
  expect(screen.getByText(/重新生成/)).toBeVisible()
  expect(screen.queryByRole('region', { name: '提取事实' })).not.toBeInTheDocument()
})
