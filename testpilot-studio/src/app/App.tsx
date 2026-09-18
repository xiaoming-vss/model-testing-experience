import { AppRoutes } from './router/routes'
import { ThemeProvider } from './providers/ThemeProvider'
import '@/app/styles/theme.css'

export default function App() {
  return (
    <ThemeProvider>
      <AppRoutes />
    </ThemeProvider>
  )
}
