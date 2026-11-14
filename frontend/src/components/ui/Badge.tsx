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
      <span
        className={cn(
          'size-1.5 rounded-full',
          active ? 'bg-emerald-500' : 'bg-slate-400',
        )}
      />
      {active ? 'فعال' : 'غیرفعال'}
    </span>
  )
}
