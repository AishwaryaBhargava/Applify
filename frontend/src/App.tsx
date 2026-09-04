import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Sidebar from './components/sidebar/Sidebar'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Onboarding from './pages/Onboarding'
import Chat from './pages/Chat'
import Profile from './pages/Profile'
import Tracker from './pages/Tracker'
import Settings from './pages/Settings'

/**
 * Auth guard placeholder.
 *
 * TODO(Phase 3): read isAuthenticated / isLoading from useAuth, render a
 * loading state while the Supabase session is restoring, and
 * <Navigate to="/login" replace /> when the user is not authenticated.
 * For now every child renders so navigation is testable.
 */
function RequireAuth({ children }: { children: ReactNode }) {
  return <>{children}</>
}

/** Shell for authenticated pages: sidebar + main area. */
function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}

/** Wraps a protected page in the auth guard and the app shell. */
function Protected({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppLayout>{children}</AppLayout>
    </RequireAuth>
  )
}

export default function App() {
  return (
    <Routes>
      {/* Public — no app shell */}
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      {/* Protected — rendered inside the sidebar shell */}
      <Route
        path="/onboarding"
        element={
          <Protected>
            <Onboarding />
          </Protected>
        }
      />
      <Route
        path="/chat"
        element={
          <Protected>
            <Chat />
          </Protected>
        }
      />
      <Route
        path="/chat/:id"
        element={
          <Protected>
            <Chat />
          </Protected>
        }
      />
      <Route
        path="/profile"
        element={
          <Protected>
            <Profile />
          </Protected>
        }
      />
      <Route
        path="/tracker"
        element={
          <Protected>
            <Tracker />
          </Protected>
        }
      />
      <Route
        path="/settings"
        element={
          <Protected>
            <Settings />
          </Protected>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
