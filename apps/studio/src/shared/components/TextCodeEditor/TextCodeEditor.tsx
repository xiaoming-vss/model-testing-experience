import { useThemeStore } from '@/shared/theme/theme.store'
import CodeMirror from '@uiw/react-codemirror'
import { indentWithTab } from '@codemirror/commands'
import { json } from '@codemirror/lang-json'
import { yaml } from '@codemirror/lang-yaml'
import { syntaxHighlighting } from '@codemirror/language'
import { EditorView, keymap } from '@codemirror/view'
import { cx } from '@/shared/utils/cx'
import '@/shared/components/RichTextEditor/rich-text-editor.css'
import {
  codeEditorTheme,
  darkCodeEditorTheme,
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
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)
  const resolvedLanguage = resolveLanguage(language, value)
  const showFoldGutter = foldable ?? resolvedLanguage !== 'plain'

  return (
    <div className={cx('json-editor-wrap flex w-full min-w-0 max-w-full flex-col gap-2', showFoldGutter && 'foldable', readOnly && 'readonly')}>
      <div className={cx('json-editor-shell w-full min-w-0 max-w-full overflow-hidden rounded-[12px] border border-[var(--app-editor-border)] bg-[var(--app-surface)] transition-[border-color,box-shadow] duration-200 ease-[ease] focus-within:border-[var(--app-editor-border-focus)] focus-within:shadow-[0_0_0_3px_var(--app-editor-focus-ring)]')}>
        <CodeMirror
          value={value ?? ''}
          theme="none"
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
            resolvedTheme === 'dark' ? darkCodeEditorTheme : codeEditorTheme,
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
