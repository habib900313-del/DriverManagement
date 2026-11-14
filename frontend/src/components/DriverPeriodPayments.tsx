import { useMemo, useState } from 'react'
import { CalendarIcon } from './icons'
import { cn } from '../lib/cn'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import type { DriverPeriodCoverage, PeriodCoverageRow } from '../types/financial'

const STATUS_STYLE: Record<
  PeriodCoverageRow['status'],
  { row: string; badge: string; label: string; bar: string }
> = {
  paid: {
    row: 'bg-emerald-50/70',
    badge: 'bg-emerald-100 text-emerald-700',
    label: 'پرداخت‌شده',
    bar: 'bg-emerald-500',
  },
  partial: {
    row: 'bg-white',
    badge: 'bg-amber-100 text-amber-700',
    label: 'پرداخت جزئی',
    bar: 'bg-emerald-500',
  },
  unpaid: {
    row: 'bg-slate-50/60',
    badge: 'bg-slate-100 text-slate-600',
    label: 'پرداخت‌نشده',
    bar: 'bg-slate-300',
  },
}

function StatusBadge({ row }: { row: PeriodCoverageRow }) {
  const style = STATUS_STYLE[row.status]
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium',
        style.badge,
      )}
    >
      {style.label}
    </span>
  )
}

export function DriverPeriodPayments({ coverage }: { coverage: DriverPeriodCoverage | null }) {
  const [selectedStart, setSelectedStart] = useState<string | null>(null)

  const rows = useMemo(() => coverage?.periods || [], [coverage])
  const selected = useMemo(
    () => rows.find((row) => row.start === selectedStart) || null,
    [rows, selectedStart],
  )

  if (!coverage || rows.length === 0) {
    return (
      <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <CalendarIcon className="size-4 text-slate-400" />
          وضعیت پرداخت دوره‌ها
        </h2>
        <p className="mt-3 text-sm text-slate-500">اطلاعاتی برای نمایش وجود ندارد.</p>
      </section>
    )
  }

  return (
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm print:border-0 print:p-0 print:shadow-none">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <CalendarIcon className="size-4 text-slate-400" />
          وضعیت پرداخت دوره‌ها
        </h2>
        <p className="text-xs text-slate-500">
          {toPersianDigits(rows.length.toString())} دوره — از گذشته تا آینده
        </p>
      </div>

      {/* The table scrolls inside itself so the profile page never grows. */}
      <div className="max-h-[20rem] overflow-y-auto overscroll-contain rounded-lg border border-slate-100">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50 text-xs text-slate-500">
            <tr>
              <th className="px-3 py-2 text-right font-medium">دوره</th>
              <th className="px-3 py-2 text-right font-medium" dir="ltr">
                پرداخت‌شده
              </th>
              <th className="px-3 py-2 text-right font-medium" dir="ltr">
                کل دوره
              </th>
              <th className="px-3 py-2 text-right font-medium" dir="ltr">
                مانده
              </th>
              <th className="px-3 py-2 text-right font-medium">وضعیت</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row) => {
              const style = STATUS_STYLE[row.status]
              const isSelected = row.start === selectedStart
              return (
                <tr
                  key={row.start}
                  onClick={() => setSelectedStart(isSelected ? null : row.start)}
                  className={cn(
                    'cursor-pointer transition hover:bg-slate-50',
                    style.row,
                    isSelected && 'ring-2 ring-inset ring-blue-400',
                  )}
                >
                  <td className="px-3 py-2">
                    <span className="block text-xs font-medium text-slate-700">
                      {formatJalaliShort(row.start)} — {formatJalaliShort(row.end)}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1 text-[10px] text-slate-400">
                      {row.is_future && <span>آینده</span>}
                      {row.is_current && <span>دوره جاری</span>}
                      {row.is_overdue && row.remaining !== '0.00' && (
                        <span className="text-rose-500">معوق</span>
                      )}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-700" dir="ltr">
                    {toPersianDigits(row.paid)}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-500" dir="ltr">
                    {toPersianDigits(row.total)}
                  </td>
                  <td
                    className={cn(
                      'px-3 py-2 font-mono text-xs',
                      row.remaining === '0.00' ? 'text-emerald-600' : 'text-slate-700',
                    )}
                    dir="ltr"
                  >
                    {toPersianDigits(row.remaining)}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge row={row} />
                    <span className="mt-1 block h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                      <span
                        className={cn('block h-full rounded-full', style.bar)}
                        style={{ width: `${Math.max(row.percent, row.status === 'paid' ? 100 : 4)}%` }}
                      />
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-semibold text-slate-700">
              جزئیات پرداخت‌های دوره {formatJalaliShort(selected.start)} —{' '}
              {formatJalaliShort(selected.end)}
            </h3>
            <button
              type="button"
              onClick={() => setSelectedStart(null)}
              className="text-[11px] text-slate-500 hover:text-slate-800"
            >
              بستن
            </button>
          </div>

          {selected.allocations.length === 0 && selected.consumptions.length === 0 ? (
            <p className="text-xs text-slate-500">برای این دوره پرداختی ثبت نشده است.</p>
          ) : (
            <ul className="space-y-1.5 text-xs text-slate-600">
              {selected.allocations.map((allocation) => (
                <li
                  key={`a-${allocation.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-200 bg-white px-2.5 py-1.5"
                >
                  <span>
                    پرداخت #{toPersianDigits(allocation.payment_id.toString())} —{' '}
                    {formatJalaliShort(allocation.payment_date)}
                    {allocation.receipt_number ? ` — رسید ${allocation.receipt_number}` : ''}
                  </span>
                  <span className="font-mono" dir="ltr">
                    {toPersianDigits(allocation.amount)} AFN
                    {allocation.reversed_at ? (
                      <span className="mr-2 text-rose-500">بازگردانده‌شده</span>
                    ) : null}
                  </span>
                </li>
              ))}
              {selected.consumptions.map((consumption) => (
                <li
                  key={`c-${consumption.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-200 bg-white px-2.5 py-1.5"
                >
                  <span>
                    مصرف اعتبار — {formatJalaliShort(consumption.effective_date)}
                    {consumption.reason ? ` — ${consumption.reason}` : ''}
                  </span>
                  <span className="font-mono" dir="ltr">
                    {toPersianDigits(consumption.amount)} AFN
                    {consumption.reversed_at ? (
                      <span className="mr-2 text-rose-500">بازگردانده‌شده</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
