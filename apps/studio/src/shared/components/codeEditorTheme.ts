import { HighlightStyle } from '@codemirror/language'
import { EditorView } from '@codemirror/view'
import { tags } from '@lezer/highlight'

export const codeEditorTheme = EditorView.theme({
  '&': {
    color: '#1f2937',
    backgroundColor: '#ffffff',
    fontFamily: "Consolas, 'Cascadia Mono', 'Courier New', monospace",
  },
  '.cm-content': { caretColor: '#111827' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: '#111827' },
  '.cm-selectionBackground, ::selection': { backgroundColor: 'rgba(96, 165, 250, 0.24)' },
  '.cm-panels': { backgroundColor: '#ffffff', color: '#1f2937' },
  '.cm-activeLine': { backgroundColor: 'rgba(15, 23, 42, 0.02)' },
  '.cm-activeLineGutter': { backgroundColor: '#ffffff' },
  '.cm-gutters': {
    backgroundColor: '#ffffff',
    color: '#94a3b8',
    borderRight: '1px solid #eef2f7',
  },
}, { dark: false })

export const jsonEditorHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: '#d97706', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.string, color: '#16a34a', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.number, color: '#d19a66', fontStyle: 'normal' },
  { tag: tags.bool, color: '#56b6c2', fontStyle: 'normal' },
  { tag: tags.null, color: '#c678dd', fontStyle: 'normal' },
  { tag: [tags.separator, tags.brace, tags.squareBracket, tags.punctuation], color: '#334155', fontWeight: '600', fontStyle: 'normal' },
])

export const yamlEditorHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: '#d97706', fontWeight: '600', fontStyle: 'normal' },
  { tag: [tags.string, tags.content], color: '#16a34a', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.number, color: '#d19a66', fontStyle: 'normal' },
  { tag: tags.bool, color: '#56b6c2', fontWeight: '600', fontStyle: 'normal' },
  { tag: tags.null, color: '#c678dd', fontStyle: 'normal' },
  { tag: tags.meta, color: '#64748b', fontWeight: '600', fontStyle: 'normal' },
  { tag: [tags.separator, tags.brace, tags.squareBracket, tags.punctuation], color: '#475569', fontWeight: '600', fontStyle: 'normal' },
])
