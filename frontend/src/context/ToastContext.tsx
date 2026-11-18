import { createContext, useCallback, useReducer, useMemo, useContext } from 'react'
import type { ReactNode } from 'react'
import {
  AlertCircleIcon,
  CheckCircleIcon,
  InfoIcon,
  XIcon,
} from '../components/icons'
import { cn } from '../lib/cn'

export type ToastType = 'success' | 'error' | 'info'

interface Toast {
  id: number
  type: ToastType
  message: string
}

interface ToastContextValue {
  notify: (type: ToastType, message: string) => void
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined)

let nextId = 1

const styles: Record<ToastType, string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  error: 'border-rose-200 bg-rose-50 text-rose-900',
  info: 'border-brand-200 bg-brand-50 text-brand-900',
}

const icons: Record<ToastType, ReactNode> = {
  success: <CheckCircleIcon className="size-5 shrink-0" />,
  error: <AlertCircleIcon className="size-5 shrink-0" />,
  info: <InfoIcon className="size-5 shrink-0" />,
}

// Type for reducer actions
type ToastAction =
  | { type: 'ADD'; payload: { type: ToastType; message: string } }
  | { type: 'DISMISS'; payload: { id: number } }

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used inside ToastProvider')
  }
  return context
}

const toastReducer = (state: Toast[], action: ToastAction) => {
  switch (action.type) {
    case 'ADD':
      const id = (state.reduce((max, t) => Math.max(max, t.id), 0) || 0) + 1
      return [...state, { id: id, type: action.payload.type, message: action.payload.message }]
    case 'DISMISS':
      return state.filter((toast) => toast.id !== action.payload.id)
    default:
      return state
  }
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, dispatch] = useReducer(toastReducer, [])

  const dismiss = useCallback((id: number) => {
    dispatch({ type: 'DISMISS', payload: { id } })
  }, [])

  const notify = useCallback(
    (type: ToastType, message: string) => {
      const id = nextId
      nextId += 1
      dispatch({ type: 'ADD', payload: { type, message } })
      window.setTimeout(() => dismiss(id), 5000)
    },
    [dismiss],
  )

  const value = useMemo<ToastContextValue>(() => ({ notify }), [notify])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-5 left-5 z-[100] flex w-[min(24rem,calc(100vw-2.5rem))] flex-col gap-2"
        role="status"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              'animate-slide-in-left pointer-events-auto flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-sm shadow-lg backdrop-blur',
              styles[toast.type],
            )}
          >
            {icons[toast.type]}
            <p className="flex-1 leading-6">{toast.message}</p>
            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              className="rounded-md p-0.5 opacity-60 transition:hover:opacity-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-current"
              aria-label="بستن پیام"
            >
              <XIcon className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}