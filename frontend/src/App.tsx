import { Suspense, lazy, useEffect, type ReactNode } from 'react'
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import Sidebar from './components/sidebar/Sidebar'
import Spinner from './components/common/Spinner'
import ToastHost from './components/common/ToastHost'
import useAuth from './hooks/useAuth'
import { setNavigator } from './lib/navigation'
import { useTrackerStore } from './store/trackerStore'

/*
 * Every page is code-split.
 *
 * The pages have almost no code in common — react-markdown belongs to the chat
 * thread alone, the tracker table to the tracker alone — so a visitor on the
 * landing page downloads the marketing page and the shell, and nothing else.
 * The route-level boundary is the natural seam: React Router only ever renders
 * one of these at a time.
 */
const Landing = lazy(() => import('./pages/Landing'))
const Login = lazy(() => import('./pages/Login'))
const Signup = lazy(() => import('./pages/Signup'))
const Onboarding = lazy(() => import('./pages/Onboarding'))
const Chat = lazy(() => import('./pages/Chat'))
const Profile = lazy(() => import('./pages/Profile'))
const Tracker = lazy(() => import('./pages/Tracker'))
const Settings = lazy(() => import('./pages/Settings'))

/** Centered spinner used while the session or profile check is resolving. */
function FullPageLoader({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg">
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

/**
 * `/` is the marketing page for a visitor and the app for a user.
 *
 * A signed-in user who lands on the root — a bookmark, the logo in a footer,
 * a link someone sent them — should get their workspace, not a pitch to sign
 * up for the thing they already pay attention to. While the session is still
 * restoring the landing page is what renders: it is the correct answer for the
 * majority of root visits, and a spinner on a public marketing page would be
 * worse than a page that resolves a moment later.
 */
function Home() {
  const { isAuthenticated, isLoading } = useAuth()

  if (!isLoading && isAuthenticated) return <Navigate to="/chat" replace />

  return <Landing />
}

/** Shell for authenticated pages: sidebar + main area. */
function AppLayout({ children }: { children: ReactNode }) {
  const fetchEntries = useTrackerStore((state) => state.fetchEntries)

  // The tracker is loaded once per session, not once per navigation: the
  // sidebar's Tracker badge reads from it on every page, and the store skips
  // the request after the first. The tracker page itself forces a refetch.
  useEffect(() => {
    void fetchEntries()
  }, [fetchEntries])

  // `overflow-hidden` rather than `overflow-y-auto`: every page inside the
  // shell owns its own scroll region (a thread with a pinned composer, a
  // profile column, a tracker table), and a second scrollbar out here would
  // move the top bar with them.
  return (
    /*
     * `h-dvh`, not `h-screen`: on a mobile browser `100vh` is the tallest the
     * viewport ever gets, so a shell sized to it sits taller than what is
     * actually visible and the page itself scrolls behind the fixed chrome.
     * The dynamic unit tracks the real viewport, which is what "no page
     * scroll, only the content scrolls" actually requires.
     */
    <div className="flex h-dvh overflow-hidden bg-bg">
      <Sidebar />
      {/*
        `relative` is load-bearing, not decoration: an absolutely positioned
        descendant with no positioned ancestor resolves against the initial
        containing block, escapes this `overflow-hidden`, and stretches the
        document — which is exactly how a `sr-only` <legend> deep inside
        Settings gave the whole app an outer scrollbar. Anchoring the
        containing block here keeps any such element inside the shell.
      */}
      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* A closer Suspense boundary than the one around the routes, so
            fetching a page's chunk swaps the main area only and leaves the
            sidebar and the drawer state exactly where they were. */}
        <Suspense fallback={<FullPageLoader label="Loading" />}>
          {children}
        </Suspense>
      </main>
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
  const navigate = useNavigate()

  // Restores the Supabase session and subscribes to auth changes exactly once.
  useEffect(() => {
    void initialize()
  }, [initialize])

  // Lets code outside React redirect — the Axios interceptor sends an expired
  // session to /login from a place that has no access to a hook.
  useEffect(() => {
    setNavigator(navigate)
    return () => setNavigator(null)
  }, [navigate])

  return (
    <>
      {/* Mounted above the routes rather than inside the signed-in shell: a
          session that expires has to be able to say so on /login too. */}
      <ToastHost />
      <Suspense fallback={<FullPageLoader label="Loading" />}>
        <Routes>
          {/* Public — no app shell */}
          <Route path="/" element={<Home />} />
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
      </Suspense>
    </>
  )
}
