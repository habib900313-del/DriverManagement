import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from 'react'
import type { ReactNode } from 'react'
import {
  AlertCircleIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  InfoIcon,
  XIcon,
} from '../components/icons'
import { cn } from '../lib/cn'

export type ToastType = 'success' | 'error' | 'info' | 'warning'

interface Toast {
  id: number
  type: ToastType
  message: string
}

interface ToastContextValue {
  notify: (type: ToastType, message: string) => void
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined)

type ToastAction =
  | { type: 'ADD'; payload: Toast }
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
      return [...state, action.payload]
    case 'DISMISS':
      return state.filter((toast) => toast.id !== action.payload.id)
    default:
      return state
  }
}

const styles: Record<ToastType, string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  error: 'border-rose-200 bg-rose-50 text-rose-900',
  info: 'border-brand-200 bg-brand-50 text-brand-900',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
}

const icons: Record<ToastType, ReactNode> = {
  success: <CheckCircleIcon className="size-5 shrink-0" />,
  error: <AlertCircleIcon className="size-5 shrink-0" />,
  info: <InfoIcon className="size-5 shrink-0" />,
  warning: <AlertTriangleIcon className="size-5 shrink-0" />,
}

function ToastItem({
  toast,
  dismiss,
}: {
  toast: Toast
  dismiss: (id: number) => void
}) {
  const toastRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timeout = window.setTimeout(
      () => dismiss(toast.id),
      toast.type === 'error' || toast.type === 'warning' ? 8000 : 5000,
    )
    const dismissOnOutsideClick = (event: MouseEvent) => {
      if (
        event.target instanceof Node &&
        !toastRef.current?.contains(event.target)
      ) {
        dismiss(toast.id)
      }
    }

    document.addEventListener('click', dismissOnOutsideClick)
    return () => {
      window.clearTimeout(timeout)
      document.removeEventListener('click', dismissOnOutsideClick)
    }
  }, [dismiss, toast.id, toast.type])

  return (
    <div
      ref={toastRef}
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
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, dispatch] = useReducer(toastReducer, [])
  const nextId = useRef(0)

  const dismiss = useCallback((id: number) => {
    dispatch({ type: 'DISMISS', payload: { id } })
  }, [])

  const notify = useCallback(
    (type: ToastType, message: string) => {
      const id = ++nextId.current
      dispatch({ type: 'ADD', payload: { id, type, message } })
    },
    [],
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
          <ToastItem
            key={toast.id}
            toast={toast}
            dismiss={dismiss}
          />
        ))}
      </div>
    </ToastContext.Provider>
  )
}