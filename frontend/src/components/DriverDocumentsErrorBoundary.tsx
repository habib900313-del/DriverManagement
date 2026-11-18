import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { AlertCircleIcon, RefreshIcon } from './icons'

interface DriverDocumentsErrorBoundaryProps {
  children: ReactNode
}

interface DriverDocumentsErrorBoundaryState {
  error: Error | null
  resetKey: number
}

export class DriverDocumentsErrorBoundary extends Component<
  DriverDocumentsErrorBoundaryProps,
  DriverDocumentsErrorBoundaryState
> {
  state: DriverDocumentsErrorBoundaryState = {
    error: null,
    resetKey: 0,
  }

  static getDerivedStateFromError(
    error: Error,
  ): Partial<DriverDocumentsErrorBoundaryState> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Driver documents section render failed.', error, info.componentStack)
  }

  private retry = () => {
    this.setState((state) => ({
      error: null,
      resetKey: state.resetKey + 1,
    }))
  }

  render() {
    if (this.state.error) {
      return (
        <section
          className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-800"
          role="alert"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="flex items-center gap-2 text-sm">
              <AlertCircleIcon className="size-4 shrink-0" />
              نمایش اسناد با خطا روبه‌رو شد؛ اطلاعات پروفایل راننده محفوظ است.
            </p>
            <button
              type="button"
              onClick={this.retry}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-rose-300 bg-white px-3 text-xs font-medium text-rose-700 shadow-xs transition hover:bg-rose-100"
            >
              <RefreshIcon className="size-4" />
              تلاش دوباره
            </button>
          </div>
        </section>
      )
    }

    return <div key={this.state.resetKey}>{this.props.children}</div>
  }
}
