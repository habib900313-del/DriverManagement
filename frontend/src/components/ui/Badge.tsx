import { cn } from '../../lib/cn'

export function StatusBadge({
  active,
  className,
}: {
  active: boolean
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
        active
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-slate-200 bg-slate-100 text-slate-600',
        className,
      )}
    >
      <span className="relative flex size-1.5">
        {active && (
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={cn(
            'relative inline-flex size-1.5 rounded-full',
            active ? 'bg-emerald-500' : 'bg-slate-400',
          )}
        />
      </span>
      {active ? 'فعال' : 'غیرفعال'}
    </span>
  )
}
