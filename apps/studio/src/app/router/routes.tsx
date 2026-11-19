import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './guards/ProtectedRoute'
import { RouteSuspense } from './RouteSuspense'

const AppShell = lazy(() => import('@/app/layouts/AppShell').then(module => ({ default: module.AppShell })))
const AuthPage = lazy(() => import('@/features/auth/pages/AuthPage').then(module => ({ default: module.AuthPage })))
const TestOrderGraphPage = lazy(() => import('@/app/pages/TestOrderGraphPage').then(module => ({ default: module.TestOrderGraphPage })))

export function AppRoutes() {
  return (
    <RouteSuspense>
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
    </RouteSuspense>
  )
}
