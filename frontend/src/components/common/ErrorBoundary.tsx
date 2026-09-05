import { Component, type ErrorInfo, type ReactNode } from 'react'
import Logo from './Logo'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  /** Kept for the development-only detail block. */
  message: string
}

/**
 * The last line of defence: a render error anywhere below this boundary is
 * caught here instead of unmounting the tree and leaving a white page.
 *
 * Mounted once around the whole app. Recovering in place is not offered — the
 * store that produced the bad render is still holding whatever caused it — so
 * the only action is a reload, which rebuilds every store from the server.
 *
 * A React error boundary has to be a class: there is no hook equivalent of
 * `componentDidCatch`.
 */
export default class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false, message: '' }

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : String(error),
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // No error reporting service is wired up yet, so the console is the only
    // record. It is the difference between a reproducible bug and a shrug.
    console.error('[applify] Unhandled render error', error, info.componentStack)
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children

    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-bg px-6 py-12 text-center">
        <Logo size={40} />
        <h1 className="mt-7 font-serif text-[26px] font-medium text-teal-ink">
          Something went wrong
        </h1>
        <p className="mt-2.5 max-w-sm text-[14px] leading-relaxed text-text-secondary">
          Applify hit an error it could not recover from. Your profile, chats,
          and applications are all saved — reloading picks up where you were.
        </p>
        <button
          type="button"
          onClick={this.handleReload}
          className="mt-7 rounded-btn bg-coral px-6 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-90"
        >
          Reload
        </button>

        {import.meta.env.DEV && this.state.message && (
          <pre className="mt-8 max-w-lg overflow-x-auto rounded-box border border-border bg-card px-4 py-3 text-left text-[12px] text-coral-ink">
            {this.state.message}
          </pre>
        )}
      </div>
    )
  }
}
