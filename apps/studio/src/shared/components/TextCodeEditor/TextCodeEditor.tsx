import CodeMirror from '@uiw/react-codemirror'
import { indentWithTab } from '@codemirror/commands'
import { json } from '@codemirror/lang-json'
import { yaml } from '@codemirror/lang-yaml'
import { syntaxHighlighting } from '@codemirror/language'
import { EditorView, keymap } from '@codemirror/view'
import {
  codeEditorTheme,
  jsonEditorHighlightStyle,
  yamlEditorHighlightStyle,
} from '../codeEditorTheme'

type TextCodeLanguage = 'plain' | 'json' | 'yaml' | 'auto'

function resolveLanguage(language: TextCodeLanguage, value?: string): Exclude<TextCodeLanguage, 'auto'> {
  if (language !== 'auto') return language
  const trimmedValue = value?.trimStart() ?? ''
  return trimmedValue.startsWith('{') || trimmedValue.startsWith('[') ? 'json' : 'yaml'
}

type TextCodeEditorProps = {
  value?: string
  onChange?: (value: string) => void
  height?: number | string
  minHeight?: number
  readOnly?: boolean
  ariaLabel?: string
  language?: TextCodeLanguage
  foldable?: boolean
}

export function TextCodeEditor({
  value,
  onChange,
  height,
  minHeight = 260,
  readOnly = false,
  ariaLabel,
  language = 'plain',
  foldable,
}: TextCodeEditorProps) {
  const resolvedLanguage = resolveLanguage(language, value)
  const showFoldGutter = foldable ?? resolvedLanguage !== 'plain'

  return (
    <div className={`json-editor-wrap${showFoldGutter ? ' foldable' : ''}${readOnly ? ' readonly' : ''}`}>
      <div className="json-editor-shell">
        <CodeMirror
          value={value ?? ''}
          height={typeof height === 'number' ? `${height}px` : height}
          minHeight={`${minHeight}px`}
          basicSetup={{
            foldGutter: showFoldGutter,
            highlightActiveLine: false,
            highlightActiveLineGutter: false,
          }}
          extensions={[
            ...(resolvedLanguage === 'json' ? [json(), syntaxHighlighting(jsonEditorHighlightStyle)] : []),
            ...(resolvedLanguage === 'yaml' ? [yaml(), syntaxHighlighting(yamlEditorHighlightStyle)] : []),
            keymap.of([indentWithTab]),
            EditorView.lineWrapping,
            codeEditorTheme,
            EditorView.contentAttributes.of({
              ...(ariaLabel ? { 'aria-label': ariaLabel } : {}),
              'aria-readonly': String(readOnly),
            }),
          ]}
          className="json-editor-codemirror"
          editable={!readOnly}
          readOnly={readOnly}
          onChange={(nextValue) => onChange?.(nextValue)}
        />
      </div>
    </div>
  )
}
