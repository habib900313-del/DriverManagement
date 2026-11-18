import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarIcon, PencilIcon } from './icons'
import { Button } from './ui/Button'
import { Spinner } from './ui/Spinner'
import { cn } from '../lib/cn'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import { fetchPayment } from '../lib/api'
import { getErrorMessage, isAbortError } from '../lib/errors'
import { getPaymentCorrectionDisabledReason } from '../lib/payments'
import type { DriverPeriodCoverage, PaymentListItem, PeriodCoverageRow } from '../types/financial'

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
  const style = getPeriodStyle(row)
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

function getPeriodStyle(row: PeriodCoverageRow) {
  if (row.is_future) {
    if (row.status === 'paid') {
      return { ...STATUS_STYLE.paid, label: 'پیش‌پرداخت‌شده' }
    }
    if (row.status === 'partial') {
      return { ...STATUS_STYLE.partial, label: 'پیش‌پرداخت جزئی' }
    }
    return {
      row: 'bg-brand-50/70',
      badge: 'bg-brand-100 text-brand-700',
      label: 'در انتظار شروع',
      bar: 'bg-brand-300',
    }
  }

  if (row.is_overdue && Number(row.remaining) > 0) {
    return {
      row: 'bg-rose-50/70',
      badge: 'bg-rose-100 text-rose-700',
      label: 'معوق',
      bar: 'bg-rose-400',
    }
  }

  const style = STATUS_STYLE[row.status]
  if (!row.is_current) return style

  return {
    ...style,
    row: row.status === 'paid' ? 'bg-emerald-50/70' : 'bg-brand-50/70',
    label:
      row.status === 'paid'
        ? 'دوره جاری — تسویه‌شده'
        : row.status === 'partial'
          ? 'دوره جاری — پرداخت جزئی'
          : 'دوره جاری — پرداخت‌نشده',
  }
}

export function DriverPeriodPayments({
  coverage,
  driverId,
  canManage = false,
}: {
  coverage: DriverPeriodCoverage | null
  driverId: number
  canManage?: boolean
}) {
  const [selectedStart, setSelectedStart] = useState<string | null>(null)
  const [paymentDetails, setPaymentDetails] = useState<{
    periodStart: string
    byId: Record<number, PaymentListItem>
  } | null>(null)
  const [paymentLoadError, setPaymentLoadError] = useState<{
    periodStart: string
    message: string
  } | null>(null)
  const [paymentRetry, setPaymentRetry] = useState(0)

  const rows = useMemo(() => coverage?.periods || [], [coverage])
  const selected = useMemo(
    () => rows.find((row) => row.start === selectedStart) || null,
    [rows, selectedStart],
  )

  useEffect(() => {
    if (!selected || selected.allocations.length === 0) {
      return
    }

    const controller = new AbortController()
    const paymentIds = [...new Set(selected.allocations.map((allocation) => allocation.payment_id))]
    Promise.all(
      paymentIds.map(async (paymentId) => [paymentId, await fetchPayment(paymentId, controller.signal)] as const),
    )
      .then((results) => {
        setPaymentDetails({
          periodStart: selected.start,
          byId: Object.fromEntries(results),
        })
      })
      .catch((cause) => {
        if (!isAbortError(cause)) {
          setPaymentLoadError({
            periodStart: selected.start,
            message: getErrorMessage(cause),
          })
        }
      })

    return () => controller.abort()
  }, [selected, paymentRetry])

  const paymentsLoading = Boolean(
    selected &&
      selected.allocations.length > 0 &&
      paymentDetails?.periodStart !== selected.start &&
      paymentLoadError?.periodStart !== selected.start,
  )
  const paymentsError =
    selected && paymentLoadError?.periodStart === selected.start
      ? paymentLoadError.message
      : null

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
              <th className="px-3 py-2 text-right font-medium">جزئیات</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row) => {
              const style = getPeriodStyle(row)
              const isSelected = row.start === selectedStart
              return (
                <tr
                  key={row.start}
                  onClick={() => setSelectedStart(isSelected ? null : row.start)}
                  className={cn(
                    'cursor-pointer transition hover:bg-slate-50',
                    style.row,
                    row.is_overdue && Number(row.remaining) > 0 && 'border-s-2 border-rose-400',
                    row.is_current && 'border-s-2 border-brand-400',
                    isSelected && 'ring-2 ring-inset ring-brand-400',
                  )}
                >
                  <td className="px-3 py-2">
                    <span className="block text-xs font-medium text-slate-700">
                      {formatJalaliShort(row.start)} — {formatJalaliShort(row.end)}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1 text-[10px] text-slate-400">
                      {row.is_future && <span>آینده</span>}
                      {row.is_current && <span>دوره جاری</span>}
                      {row.is_overdue && Number(row.remaining) > 0 && (
                        <span className="text-rose-500">سررسید گذشته</span>
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
                  <td className="px-3 py-2">
                    {row.allocations.length > 0 && (
                      <button
                        type="button"
                        aria-expanded={isSelected}
                        onClick={(event) => {
                          event.stopPropagation()
                          setSelectedStart(isSelected ? null : row.start)
                        }}
                        className="whitespace-nowrap rounded-lg px-2 py-1 text-[11px] font-medium text-brand-700 transition hover:bg-brand-50"
                      >
                        {isSelected ? 'بستن جزئیات' : 'مشاهده پرداخت‌ها'}
                      </button>
                    )}
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
            <div className="space-y-2">
              {paymentsLoading && (
                <p className="flex items-center gap-2 text-xs text-slate-500">
                  <Spinner className="size-4" />
                  در حال بارگذاری جزئیات پرداخت‌ها…
                </p>
              )}
              {paymentsError && (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700" role="alert">
                  <span>جزئیات پرداخت بارگذاری نشد: {paymentsError}</span>
                  <button
                    type="button"
                    className="font-semibold underline underline-offset-2"
                    onClick={() => {
                      setPaymentLoadError(null)
                      setPaymentRetry((current) => current + 1)
                    }}
                  >
                    تلاش دوباره
                  </button>
                </div>
              )}
              <ul className="space-y-1.5 text-xs text-slate-600">
              {selected.allocations.map((allocation) => {
                const payment =
                  paymentDetails?.periodStart === selected.start
                    ? paymentDetails.byId[allocation.payment_id]
                    : undefined
                const disabledReason = payment
                  ? getPaymentCorrectionDisabledReason(payment)
                  : paymentsError
                    ? 'جزئیات پرداخت برای بررسی امکان اصلاح در دسترس نیست.'
                    : 'در حال بررسی وضعیت پرداخت…'
                const correctionUrl =
                  `/financial/payments/${allocation.payment_id}/correct` +
                  `?returnTo=${encodeURIComponent(`/drivers/${driverId}`)}`

                return (
                  <li
                    key={`a-${allocation.id}`}
                    className="flex flex-col gap-2 rounded border border-slate-200 bg-white px-2.5 py-2 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <span className="min-w-0">
                      پرداخت #{toPersianDigits(allocation.payment_id.toString())} —{' '}
                      {formatJalaliShort(allocation.payment_date)}
                      {allocation.receipt_number ? ` — رسید ${allocation.receipt_number}` : ''}
                      {allocation.description ? ` — ${allocation.description}` : ''}
                      {allocation.reversed_at ? (
                        <span className="mr-2 text-rose-500">بازگردانده‌شده</span>
                      ) : null}
                      <span className="mr-2 font-mono" dir="ltr">
                        {toPersianDigits(allocation.amount)} AFN
                      </span>
                    </span>
                    {canManage && (
                      <div className="flex shrink-0 flex-wrap items-center gap-2">
                        {payment && !disabledReason ? (
                          <Link
                            to={correctionUrl}
                            className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 text-xs font-semibold text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
                          >
                            <PencilIcon className="size-3.5" />
                            اصلاح پرداخت
                          </Link>
                        ) : (
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            disabled
                            title={disabledReason ?? undefined}
                          >
                            اصلاح پرداخت
                          </Button>
                        )}
                        {disabledReason && !paymentsLoading && (
                          <span className="max-w-56 text-[11px] leading-4 text-amber-700">
                            {disabledReason}
                          </span>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
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
            </div>
          )}
        </div>
      )}
    </section>
  )
}
