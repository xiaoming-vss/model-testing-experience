import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AppErrorBoundary } from './providers/AppErrorBoundary'
import { QueryProvider } from './providers/QueryProvider'
import { installChunkLoadRecovery } from '@/shared/utils/chunkLoadRecovery'
import '@/index.css'
import App from './App'

installChunkLoadRecovery()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <QueryProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryProvider>
    </AppErrorBoundary>
  </StrictMode>,
)
