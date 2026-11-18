import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      {icon && (
        <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-b from-brand-50 to-brand-100 text-brand-500 ring-1 ring-brand-100 ring-offset-2">
          {icon}
        </div>
      )}
      <div>
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        {description && (
          <p className="mt-1 max-w-md text-sm leading-6 text-slate-500">
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  )
}
