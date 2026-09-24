import { HighlightStyle } from '@codemirror/language'
import { EditorView } from '@codemirror/view'
import { tags } from '@lezer/highlight'

const editorStyle = {
  '&': {
    color: 'var(--editor-text)',
    backgroundColor: 'var(--editor-bg)',
    fontFamily: "Consolas, 'Cascadia Mono', 'Courier New', monospace",
  },
  '.cm-content': { caretColor: 'var(--editor-caret)' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--editor-caret)' },
  '.cm-selectionBackground, ::selection': { backgroundColor: 'var(--editor-selection)' },
  '.cm-panels': { backgroundColor: 'var(--editor-bg)', color: 'var(--editor-text)' },
  '.cm-activeLine': { backgroundColor: 'var(--editor-active-line)' },
  '.cm-activeLineGutter': { backgroundColor: 'var(--editor-bg)' },
  '.cm-gutters': {
    backgroundColor: 'var(--editor-bg)',
    color: 'var(--editor-gutter-text)',
    borderRight: '1px solid var(--editor-gutter-border)',
  },
}

export const codeEditorTheme = EditorView.theme(editorStyle, { dark: false })
export const darkCodeEditorTheme = EditorView.theme(editorStyle, { dark: true })

export const jsonEditorHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: 'var(--editor-syntax-key)', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.string, color: 'var(--editor-syntax-string)', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.number, color: 'var(--editor-syntax-number)', fontStyle: 'normal' },
  { tag: tags.bool, color: 'var(--editor-syntax-boolean)', fontStyle: 'normal' },
  { tag: tags.null, color: 'var(--editor-syntax-null)', fontStyle: 'normal' },
  { tag: [tags.separator, tags.brace, tags.squareBracket, tags.punctuation], color: 'var(--editor-syntax-json-punctuation)', fontWeight: '600', fontStyle: 'normal' },
])

export const yamlEditorHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: 'var(--editor-syntax-key)', fontWeight: '600', fontStyle: 'normal' },
  { tag: [tags.string, tags.content], color: 'var(--editor-syntax-string)', fontWeight: '500', fontStyle: 'normal' },
  { tag: tags.number, color: 'var(--editor-syntax-number)', fontStyle: 'normal' },
  { tag: tags.bool, color: 'var(--editor-syntax-boolean)', fontWeight: '600', fontStyle: 'normal' },
  { tag: tags.null, color: 'var(--editor-syntax-null)', fontStyle: 'normal' },
  { tag: tags.meta, color: 'var(--editor-syntax-meta)', fontWeight: '600', fontStyle: 'normal' },
  { tag: [tags.separator, tags.brace, tags.squareBracket, tags.punctuation], color: 'var(--editor-syntax-yaml-punctuation)', fontWeight: '600', fontStyle: 'normal' },
])
