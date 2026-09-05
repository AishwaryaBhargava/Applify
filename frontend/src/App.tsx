import { useEffect, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Sidebar from './components/sidebar/Sidebar'
import Spinner from './components/common/Spinner'
import useAuth from './hooks/useAuth'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Onboarding from './pages/Onboarding'
import Chat from './pages/Chat'
import Profile from './pages/Profile'
import Tracker from './pages/Tracker'
import Settings from './pages/Settings'

/** Centered spinner used while the session or profile check is resolving. */
function FullPageLoader({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <div className="flex flex-col items-center gap-3">
        <Spinner size={24} label={label} className="text-teal-deep" />
        <p className="text-[13px] text-text-muted">{label}</p>
      </div>
    </div>
  )
}

/**
 * Auth guard.
 *
 * - session still restoring -> full page spinner (no flicker, no redirect loop)
 * - signed out              -> /login, remembering where the user was headed
 * - profile not checked yet -> check it, spinner meanwhile
 * - no profile, not skipped -> /onboarding
 * - otherwise               -> render the page
 */
function RequireAuth({ children }: { children: ReactNode }) {
  const {
    isAuthenticated,
    isLoading,
    hasProfile,
    skippedOnboarding,
    checkProfile,
  } = useAuth()
  const location = useLocation()

  useEffect(() => {
    if (isAuthenticated && hasProfile === null) {
      void checkProfile()
    }
  }, [isAuthenticated, hasProfile, checkProfile])

  if (isLoading) return <FullPageLoader label="Restoring your session" />

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (hasProfile === null) return <FullPageLoader label="Loading your profile" />

  if (
    hasProfile === false &&
    !skippedOnboarding &&
    location.pathname !== '/onboarding'
  ) {
    return <Navigate to="/onboarding" replace />
  }

  return <>{children}</>
}

/** Keeps signed-in users out of /login and /signup. */
function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) return <FullPageLoader label="Restoring your session" />
  if (isAuthenticated) return <Navigate to="/chat" replace />

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
  const { initialize } = useAuth()

  // Restores the Supabase session and subscribes to auth changes exactly once.
  useEffect(() => {
    void initialize()
  }, [initialize])

  return (
    <Routes>
      {/* Public — no app shell */}
      <Route path="/" element={<Landing />} />
      <Route
        path="/login"
        element={
          <RedirectIfAuthenticated>
            <Login />
          </RedirectIfAuthenticated>
        }
      />
      <Route
        path="/signup"
        element={
          <RedirectIfAuthenticated>
            <Signup />
          </RedirectIfAuthenticated>
        }
      />

      {/* Protected, but deliberately outside the sidebar shell: onboarding is
          a focused single-purpose page. */}
      <Route
        path="/onboarding"
        element={
          <RequireAuth>
            <Onboarding />
          </RequireAuth>
        }
      />

      {/* Protected — rendered inside the sidebar shell */}
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
