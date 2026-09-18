import { HighlightStyle } from '@codemirror/language'
import { EditorView } from '@codemirror/view'
import { tags } from '@lezer/highlight'

export const codeEditorLightTheme = EditorView.theme({
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

export const codeEditorDarkTheme = EditorView.theme({
  '&': {
    color: '#e5edf9',
    backgroundColor: '#1f2431',
    fontFamily: "Consolas, 'Cascadia Mono', 'Courier New', monospace",
  },
  '.cm-content': { caretColor: '#dbeafe' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: '#dbeafe', borderLeftWidth: '2px' },
  '.cm-selectionBackground, ::selection': { backgroundColor: 'rgba(96, 165, 250, 0.28)' },
  '.cm-panels': { backgroundColor: '#1f2431', color: '#e5edf9' },
  '.cm-activeLine': { backgroundColor: 'rgba(148, 163, 184, 0.06)' },
  '.cm-activeLineGutter': { backgroundColor: '#1f2431' },
  '.cm-gutters': {
    backgroundColor: '#1f2431',
    color: '#71839e',
    borderRight: '1px solid rgba(148, 163, 184, 0.16)',
  },
}, { dark: true })

export const jsonEditorLightHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: '#d97706', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.string, color: '#16a34a', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.number, color: '#d19a66', fontStyle: 'normal' },
  { tag: tags.bool, color: '#56b6c2', fontStyle: 'normal' },
  { tag: tags.null, color: '#c678dd', fontStyle: 'normal' },
  { tag: [tags.separator, tags.brace, tags.squareBracket, tags.punctuation], color: '#334155', fontWeight: '600', fontStyle: 'normal' },
])

export const jsonEditorDarkHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: '#f59e0b', fontWeight: '600', fontStyle: 'normal' },
  { tag: tags.string, color: '#4ade80', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.number, color: '#f7b267', fontStyle: 'normal' },
  { tag: tags.bool, color: '#67e8f9', fontStyle: 'normal' },
  { tag: tags.null, color: '#d8b4fe', fontStyle: 'normal' },
  { tag: [tags.separator, tags.brace, tags.squareBracket, tags.punctuation], color: '#9fb7d6', fontWeight: '700', fontStyle: 'normal' },
])

export const yamlEditorLightHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: '#d97706', fontWeight: '600', fontStyle: 'normal' },
  { tag: [tags.string, tags.content], color: '#16a34a', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.number, color: '#d19a66', fontStyle: 'normal' },
  { tag: tags.bool, color: '#56b6c2', fontWeight: '600', fontStyle: 'normal' },
  { tag: tags.null, color: '#c678dd', fontStyle: 'normal' },
  { tag: tags.meta, color: '#64748b', fontWeight: '600', fontStyle: 'normal' },
  { tag: [tags.separator, tags.brace, tags.squareBracket, tags.punctuation], color: '#475569', fontWeight: '600', fontStyle: 'normal' },
])

export const yamlEditorDarkHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: '#f59e0b', fontWeight: '600', fontStyle: 'normal' },
  { tag: [tags.string, tags.content], color: '#4ade80', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.number, color: '#f7b267', fontStyle: 'normal' },
  { tag: tags.bool, color: '#67e8f9', fontWeight: '600', fontStyle: 'normal' },
  { tag: tags.null, color: '#d8b4fe', fontStyle: 'normal' },
  { tag: tags.meta, color: '#94a3b8', fontWeight: '600', fontStyle: 'normal' },
  { tag: [tags.separator, tags.brace, tags.squareBracket, tags.punctuation], color: '#9fb7d6', fontWeight: '700', fontStyle: 'normal' },
])
