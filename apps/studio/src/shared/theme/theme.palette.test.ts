import { describe, expect, it } from 'vitest'
import foundation from '../styles/foundation-tokens.css?raw'
import editor from '../styles/editor-tokens.css?raw'
import charts from '../styles/chart-tokens.css?raw'
import legacy from '../styles/legacy-tokens.css?raw'
import darkFoundation from '../styles/github-dark-foundation.css?raw'
import dark from '../styles/github-dark-tokens.css?raw'
import buttons from '../../app/styles/buttons.css?raw'
import light from '../styles/indigo-amber-light-tokens.css?raw'
import surfaces from '../styles/surface-tokens.css?raw'

function declarations(css: string) {
  return new Map([...css.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]))
}

describe('light workbench surfaces', () => {
  // Resolve the actual global and content-surface token blocks; sidebar aliases
  // are a separate local scope and must not replace content roles in this map.
  const global = light.match(/:root:not\(\[data-theme='dark'\]\)\s*\{([^}]+)\}/)?.[1] ?? ''
  const content = light.match(/:root:not\(\[data-theme='dark'\]\) \.tp-surface\s*\{([^}]+)\}/)?.[1] ?? ''
  const values = declarations(foundation + legacy + surfaces + buttons + editor + global + content)
  function resolve(name: string, seen: string[] = []): string {
    expect(seen, `cycle at ${name}`).not.toContain(name)
    expect(values.has(name), `missing ${name}`).toBe(true)
    return values.get(name)!.replace(/var\((--[\w-]+)\)/g, (_, ref: string) => resolve(ref, [...seen, name]))
  }
  it('keeps legacy glass panels, populated rows and modern cards in the same muted palette', () => {
    const panel = resolve('--app-surface')
    for (const role of [
      '--srf-card', '--srf-list-row-bg', '--legacy-mac-glass-panel', '--legacy-mac-glass-card',
      '--app-glass-surface-50', '--app-glass-surface-54', '--app-glass-surface-62',
      '--app-glass-surface-66', '--app-glass-surface-68', '--app-glass-surface-70',
      '--app-glass-surface-72', '--app-glass-surface-78', '--app-glass-surface-82',
      '--app-glass-surface-86', '--app-glass-surface-96', '--app-glass-surface-98',
      '--app-glass-table-bg', '--app-glass-toolbar', '--legacy-project-overview-panel',
    ]) expect(resolve(role), role).toBe(panel)
    expect(resolve('--srf-hover')).toBe(resolve('--srf-list-header-bg'))
  })
  it('does not apply any light palette rule to dark root, sidebar or content nodes', () => {
    const previousTheme = document.documentElement.dataset.theme
    const fixture = document.createElement('div')
    fixture.innerHTML = '<aside class="app-sidebar"></aside><main class="tp-surface"><span class="tone-blue"></span></main>'
    document.body.append(fixture)
    document.documentElement.dataset.theme = 'dark'
    try {
      const nodes = [document.documentElement, ...fixture.querySelectorAll('*')]
      const css = light.replace(/\/\*[\s\S]*?\*\//g, '')
      for (const block of css.matchAll(/([^{}]+)\{[^}]+\}/g)) {
        for (const node of nodes) expect(node.matches(block[1].trim()), block[1]).toBe(false)
      }
    } finally {
      fixture.remove()
      if (previousTheme === undefined) delete document.documentElement.dataset.theme
      else document.documentElement.dataset.theme = previousTheme
    }
  })
  it('keeps normal and disabled controls in the same surface palette as their containers', () => {
    for (const role of ['--button-bg', '--app-control-surface', '--app-glass-input', '--app-request-field-bg', '--editor-bg']) {
      expect(resolve(role), role).toBe(resolve('--app-surface'))
    }
    expect(resolve('--button-disabled-bg')).toBe(resolve('--srf-list-header-bg'))
    expect(resolve('--button-hover-bg')).toBe(resolve('--srf-list-header-bg'))
    expect(resolve('--srf-chip')).toBe(resolve('--srf-list-header-bg'))
  })
  it('removes white glass highlights and aligns glass edges with the neutral border palette', () => {
    for (const name of declarations(foundation).keys()) {
      if (/^--app-glass-highlight-\d+$/.test(name)) expect(resolve(name), name).toBe('transparent')
      if (/^--app-glass-border-\d+$/.test(name)) expect(resolve(name), name).toBe(resolve('--app-surface-border'))
    }
  })
})

describe('dark palette contract', () => {
  const colors = declarations(dark + darkFoundation)
  function resolve(name: string, seen: string[] = []): string {
    expect(seen, `cycle at ${name}`).not.toContain(name)
    expect(colors.has(name), `missing ${name}`).toBe(true)
    return colors.get(name)!.replace(/var\((--[\w-]+)\)/g, (_, ref: string) => resolve(ref, [...seen, name]))
  }
  it('provides a dark value for every foundation, editor, chart and legacy role except brand artwork', () => {
    const brand = new Set(['--app-logo-primary', '--app-logo-shadow', '--app-logo-border', '--app-logo-model-text', '--app-logo-secondary'])
    // Geometry is shared by both themes and does not need a dark color mapping.
    const geometry = new Set(['--app-scrollbar-size', '--app-scrollbar-radius'])
    for (const name of declarations(foundation + editor + charts + legacy).keys()) {
      if (!brand.has(name) && !geometry.has(name)) expect(colors.has(name), name).toBe(true)
    }
  })

  it('resolves every dark alias without missing references or cycles', () => {
    for (const name of colors.keys()) resolve(name)
    expect(resolve('--graph-export-background')).toBe('#0d1117')
    expect(resolve('--graph-export-border')).toBe('1px solid #30363d')
  })

  it('keeps status and hover text readable against their tinted backgrounds', () => {
    const rgb = (color: string) => color.startsWith('#')
      ? color.slice(1).match(/../g)!.map((channel) => parseInt(channel, 16))
      : color.match(/[\d.]+/g)!.map(Number)
    const luminance = (channels: number[]) => channels.slice(0, 3).map((value) => {
      const channel = value / 255
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    }).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0)
    const foreground = luminance(rgb(resolve('--app-accent')))
    const surface = rgb(resolve('--gh-surface'))
    for (const role of ['--app-accent-emphasis', '--app-request-add-hover']) {
      const background = rgb(resolve(role))
      const alpha = background[3] ?? 1
      const composited = background.slice(0, 3).map((value, index) => value * alpha + surface[index] * (1 - alpha))
      const contrast = (foreground + 0.05) / (luminance(composited) + 0.05)
      expect(contrast, role).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('gives link buttons an independent accent instead of filled-button text', () => {
    const rule = buttons.match(/\.ant-btn-link:not\([^{}]+\{([^}]+)\}/)?.[1] ?? ''
    const textRole = declarations(rule).get('--button-current-text')?.match(/var\((--[\w-]+)\)/)?.[1]
    expect(textRole).toBeDefined()
    expect(resolve(textRole!)).toBe(resolve('--app-link'))
    expect(resolve(textRole!)).not.toBe(resolve('--button-primary-text'))
    const lightColors = declarations(buttons)
    expect(lightColors.get(textRole!)).toBe(lightColors.get('--button-primary-text'))
  })

  it('keeps dark styles limited to custom properties', () => {
    for (const css of [dark, darkFoundation]) {
      const blocks = css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/\{([^}]+)\}/g)
      for (const block of blocks) {
        for (const declaration of block[1].split(';').filter((value) => value.trim())) {
          expect(declaration.trim()).toMatch(/^--[\w-]+\s*:/)
        }
      }
    }
  })
})
