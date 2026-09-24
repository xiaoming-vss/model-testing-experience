import { DesktopOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Button, Tooltip } from 'antd'
import { useThemeStore } from '@/shared/theme/theme.store'

const modes = {
  light: { label: '浅色', next: 'dark', icon: SunOutlined },
  dark: { label: '深色', next: 'system', icon: MoonOutlined },
  system: { label: '跟随系统', next: 'light', icon: DesktopOutlined },
} as const

export function ThemeSelect() {
  const preference = useThemeStore((state) => state.preference)
  const setPreference = useThemeStore((state) => state.setPreference)
  const mode = modes[preference]
  const Icon = mode.icon
  const label = `当前主题：${mode.label}，点击切换为${modes[mode.next].label}`
  return (
    <Tooltip title={label}>
      <Button
        type="text"
        aria-label={label}
        icon={<Icon />}
        onClick={() => setPreference(mode.next)}
      />
    </Tooltip>
  )
}
