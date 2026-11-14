import { describe, expect, it } from 'vitest'
import { assetTabForLocation, navigationIndex, testingTabForLocation } from './navigation'

describe('top-level navigation resolution', () => {
  it('moves the case library out of the testing workspace', () => {
    expect(testingTabForLocation('/testing', '?tab=orders')).toBe('orders')
    expect(testingTabForLocation('/testing', '?tab=api')).toBe('api')
    expect(testingTabForLocation('/testing', '?tab=ui')).toBe('ui')
    expect(testingTabForLocation('/test-cases', '')).toBeNull()
    expect(testingTabForLocation('/test-cases/12', '')).toBeNull()
  })

  it('treats every asset-library route as asset navigation', () => {
    expect(assetTabForLocation('/asset-library', '')).toBe('cases')
    expect(assetTabForLocation('/asset-library', '?tab=interfaces')).toBe('interfaces')
    expect(assetTabForLocation('/asset-library', '?tab=apps')).toBe('apps')
    expect(assetTabForLocation('/asset-library/interfaces/new', '')).toBe('interfaces')
    expect(assetTabForLocation('/asset-library/interfaces/api-1', '')).toBe('interfaces')
    expect(assetTabForLocation('/testing', '?tab=cases')).toBeNull()
  })

  it('orders the navigation indices without making legacy test-case paths testing', () => {
    expect(navigationIndex('/projects', '?board=sprints', false)).toBe(0)
    expect(navigationIndex('/requirements/req-1', '', false)).toBe(1)
    expect(navigationIndex('/testing', '?tab=api', false)).toBe(2)
    expect(navigationIndex('/asset-library?tab=interfaces', '?tab=interfaces', false)).toBe(3)
    expect(navigationIndex('/testing', '?tab=bugs', false)).toBe(4)
    expect(navigationIndex('/base-services', '', false)).toBe(5)
    expect(navigationIndex('/test-cases/12', '', false)).toBeNull()
  })

  it('keeps bug-only projects restricted to the bug navigation index', () => {
    expect(navigationIndex('/testing', '?tab=bugs', true)).toBe(4)
    expect(navigationIndex('/testing', '?tab=api', true)).toBeNull()
    expect(navigationIndex('/asset-library?tab=interfaces', '?tab=interfaces', true)).toBeNull()
  })
})
