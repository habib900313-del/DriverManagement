import { cn } from '../../lib/cn'
import { toPersianDigits } from '../../lib/dates'
import { ChevronLeftIcon, ChevronRightIcon } from '../icons'

interface PaginationProps {
  page: number
  totalPages: number
  totalItems?: number
  onChange: (page: number) => void
}

type PageItem = number | 'dots'

function getPageItems(current: number, total: number): PageItem[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1)
  }

  const items: PageItem[] = [1]
  if (current > 3) items.push('dots')

  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)
  for (let page = start; page <= end; page += 1) items.push(page)

  if (current < total - 2) items.push('dots')
  items.push(total)
  return items
}

export function Pagination({
  page,
  totalPages,
  totalItems,
  onChange,
}: PaginationProps) {
  if (totalPages <= 1) return null

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3">
      <p className="text-xs text-slate-500">
        صفحه {toPersianDigits(page)} از {toPersianDigits(totalPages)}
        {typeof totalItems === 'number' &&
          ` — ${toPersianDigits(totalItems)} راننده`}
      </p>
      <nav className="flex items-center gap-1" aria-label="صفحه‌بندی">
        <button
          type="button"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          className="inline-flex size-8 items-center justify-center rounded-lg border border-slate-200 text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-40"
          aria-label="صفحه قبلی"
        >
          <ChevronRightIcon className="size-4" />
        </button>

        {getPageItems(page, totalPages).map((item, index) =>
          item === 'dots' ? (
            <span
              key={`dots-${index}`}
              className="inline-flex size-8 items-center justify-center text-xs text-slate-400"
            >
              …
            </span>
          ) : (
            <button
              key={item}
              type="button"
              onClick={() => onChange(item)}
              aria-current={item === page ? 'page' : undefined}
              className={cn(
                'inline-flex size-8 items-center justify-center rounded-lg text-xs font-medium transition',
                item === page
                  ? 'bg-gradient-to-b from-brand-500 to-brand-600 text-white shadow-sm shadow-brand-600/25'
                  : 'border border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50',
              )}
            >
              {toPersianDigits(item)}
            </button>
          ),
        )}

        <button
          type="button"
          onClick={() => onChange(page + 1)}
          disabled={page >= totalPages}
          className="inline-flex size-8 items-center justify-center rounded-lg border border-slate-200 text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-40"
          aria-label="صفحه بعدی"
        >
          <ChevronLeftIcon className="size-4" />
        </button>
      </nav>
    </div>
  )
}
