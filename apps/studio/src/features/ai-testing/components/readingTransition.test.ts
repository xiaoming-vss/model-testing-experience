import { afterEach, describe, expect, it, vi } from 'vitest'
import { animateInspectorContents, animateReadingExit, setReadingOrigin } from './readingTransition'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('canvas reading transition', () => {
  it('uses the card centre within the canvas', () => {
    const stage = document.createElement('div')
    const card = document.createElement('button')
    vi.spyOn(stage, 'getBoundingClientRect').mockReturnValue({ left: 100, top: 50, width: 400, height: 200 } as DOMRect)
    vi.spyOn(card, 'getBoundingClientRect').mockReturnValue({ left: 380, top: 100, width: 40, height: 20 } as DOMRect)
    setReadingOrigin(stage, card)
    expect(stage.style.getPropertyValue('--gc-reading-origin-x')).toBe('75%')
    expect(stage.style.getPropertyValue('--gc-reading-origin-y')).toBe('30%')
    setReadingOrigin(stage)
    expect(stage.style.getPropertyValue('--gc-reading-origin-x')).toBe('')
  })

  it('keeps the reader mounted until its reverse animation finishes', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const stage = document.createElement('div')
    const reader = document.createElement('section')
    reader.className = 'gc-embedded-artifact'
    stage.append(reader)
    const animation = { onfinish: null as (() => void) | null }
    const animate = vi.fn(() => animation)
    Object.defineProperty(reader, 'animate', { value: animate })
    const finish = vi.fn()
    expect(animateReadingExit(stage, finish)).toBe(animation)
    expect(finish).not.toHaveBeenCalled()
    expect(animate).toHaveBeenCalledWith(
      [{ opacity: 1, transform: 'scale(1)' }, { opacity: 0, transform: 'scale(.93)' }],
      { duration: 260, easing: 'ease-in', fill: 'forwards' },
    )
    animation.onfinish?.()
    expect(finish).toHaveBeenCalledTimes(1)
  })

  it('returns immediately when reduced motion is requested', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const stage = document.createElement('div')
    const reader = document.createElement('section')
    reader.className = 'gc-embedded-artifact'
    const animate = vi.fn()
    Object.defineProperty(reader, 'animate', { value: animate })
    stage.append(reader)
    const finish = vi.fn()
    expect(animateReadingExit(stage, finish)).toBeNull()
    expect(finish).toHaveBeenCalledTimes(1)
    expect(animate).not.toHaveBeenCalled()
  })
  it('animates inspector contents without moving the inspector shell', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const inspector = document.createElement('aside')
    inspector.innerHTML = '<div class="gc-inspector-header"></div><div class="gc-inspector-content"></div><div class="gc-inspector-footer"></div>'
    const shellAnimate = vi.fn()
    Object.defineProperty(inspector, 'animate', { value: shellAnimate })
    const elements = Array.from(inspector.children)
    const animate = vi.fn(() => ({ id: '' }))
    elements.forEach(element => Object.defineProperty(element, 'animate', { value: animate }))
    animateInspectorContents(inspector)
    expect(shellAnimate).not.toHaveBeenCalled()
    expect(animate).toHaveBeenCalledTimes(3)
    expect(animate).toHaveBeenCalledWith(
      [{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'translateY(0)' }],
      { duration: 320, easing: 'cubic-bezier(.22, 1, .36, 1)' },
    )
  })

  it('skips the inspector transition for reduced motion', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const inspector = document.createElement('aside')
    inspector.innerHTML = '<div class="gc-inspector-header"></div>'
    const animate = vi.fn()
    Object.defineProperty(inspector.firstElementChild, 'animate', { value: animate })
    animateInspectorContents(inspector)
    expect(animate).not.toHaveBeenCalled()
  })

})
