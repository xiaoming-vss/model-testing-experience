import { waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installTabMotion } from './tabMotion'

afterEach(() => { document.body.innerHTML = ''; vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('tab motion', () => {
  it('moves the indicator and animates the corresponding panel in both directions', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    document.body.innerHTML = `<div data-tab-motion-scope><div role="tablist" data-tab-motion-scoped>
      <button role="tab" aria-selected="true">A</button><button role="tab" aria-selected="false">B</button>
      </div><div data-tab-motion-panel></div></div>`
    const list = document.querySelector<HTMLElement>('[role=tablist]')!
    const panel = document.querySelector<HTMLElement>('[data-tab-motion-panel]')!
    const animate = vi.fn(() => ({ id: '', cancel: vi.fn() }))
    Object.defineProperty(panel, 'animate', { value: animate })
    const stop = installTabMotion(document.body)
    expect(list.querySelector('.shared-tab-motion-indicator')).not.toBeNull()
    const tabs = list.querySelectorAll('[role=tab]')
    tabs[0].setAttribute('aria-selected', 'false')
    tabs[1].setAttribute('aria-selected', 'true')
    await waitFor(() => expect(animate).toHaveBeenCalledTimes(1))
    expect(animate).toHaveBeenLastCalledWith(
      [{ opacity: 0, transform: 'translateX(22px)' }, { opacity: 1, transform: 'translateX(0)' }],
      { duration: 340, easing: 'cubic-bezier(.22, 1, .36, 1)' },
    )
    tabs[1].setAttribute('aria-selected', 'false')
    tabs[0].setAttribute('aria-selected', 'true')
    await waitFor(() => expect(animate).toHaveBeenCalledTimes(2))
    expect(animate).toHaveBeenLastCalledWith(
      [{ opacity: 0, transform: 'translateX(-22px)' }, { opacity: 1, transform: 'translateX(0)' }],
      { duration: 340, easing: 'cubic-bezier(.22, 1, .36, 1)' },
    )
    stop()
    expect(list.querySelector('.shared-tab-motion-indicator')).toBeNull()
  })

  it('supports newly mounted tabs and respects reduced motion', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const stop = installTabMotion(document.body)
    document.body.innerHTML = `<div role="tablist"><button role="tab" aria-selected="true" aria-controls="a">A</button><button role="tab" aria-selected="false" aria-controls="b">B</button></div><div id="b"></div>`
    await waitFor(() => expect(document.querySelector('.shared-tab-motion-indicator')).not.toBeNull())
    const animate = vi.fn()
    Object.defineProperty(document.getElementById('b'), 'animate', { value: animate })
    const tabs = document.querySelectorAll('[role=tab]')
    tabs[0].setAttribute('aria-selected', 'false')
    tabs[1].setAttribute('aria-selected', 'true')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(animate).not.toHaveBeenCalled()
    stop()
  })
  it('tracks a nested Ant Design tab list without moving its ink independently of scrolling', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    document.body.innerHTML = `<div role="tablist"><div class="ant-tabs-nav-list">
      <div class="ant-tabs-tab"><div role="tab" aria-selected="true" aria-controls="a">A</div></div>
      <div class="ant-tabs-tab"><div role="tab" aria-selected="false" aria-controls="b">B</div></div>
      </div></div><div id="b"></div>`
    const target = document.getElementById('b')!
    const animate = vi.fn(() => ({ id: '' }))
    Object.defineProperty(target, 'animate', { value: animate })
    const stop = installTabMotion(document.body)
    expect(document.querySelector('.ant-tabs-nav-list > .shared-tab-motion-indicator')).not.toBeNull()
    const tabs = document.querySelectorAll('[role=tab]')
    tabs[0].setAttribute('aria-selected', 'false')
    tabs[1].setAttribute('aria-selected', 'true')
    await waitFor(() => expect(animate).toHaveBeenCalledTimes(1))
    stop()
  })

})
