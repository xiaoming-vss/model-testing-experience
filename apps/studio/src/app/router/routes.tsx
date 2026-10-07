import { Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './guards/ProtectedRoute'
import { AppShell } from '@/app/layouts/AppShell'
import { AuthPage } from '@/features/auth/pages/AuthPage'
import { TestOrderGraphPage } from '@/app/pages/TestOrderGraphPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route path="/test-orders/:orderId/graph" element={<ProtectedRoute><TestOrderGraphPage /></ProtectedRoute>} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}
