import { describe, expect, it } from 'vitest'
import foundation from '../styles/foundation-tokens.css?raw'
import editor from '../styles/editor-tokens.css?raw'
import charts from '../styles/chart-tokens.css?raw'
import legacy from '../styles/legacy-tokens.css?raw'
import darkFoundation from '../styles/github-dark-foundation.css?raw'
import dark from '../styles/github-dark-tokens.css?raw'
import buttons from '../../app/styles/buttons.css?raw'

function declarations(css: string) {
  return new Map([...css.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]))
}

describe('dark palette contract', () => {
  const colors = declarations(dark + darkFoundation)
  function resolve(name: string, seen: string[] = []): string {
    expect(seen, `cycle at ${name}`).not.toContain(name)
    expect(colors.has(name), `missing ${name}`).toBe(true)
    return colors.get(name)!.replace(/var\((--[\w-]+)\)/g, (_, ref: string) => resolve(ref, [...seen, name]))
  }
  it('provides a dark value for every foundation, editor, chart and legacy role except brand artwork', () => {
    const brand = new Set(['--app-logo-primary', '--app-logo-shadow', '--app-logo-border', '--app-logo-model-text', '--app-logo-secondary'])
    for (const name of declarations(foundation + editor + charts + legacy).keys()) {
      if (!brand.has(name)) expect(colors.has(name), name).toBe(true)
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
