import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRightIcon, CalendarIcon, CreditCardIcon, RefreshIcon } from '../components/icons'
import { StatusBadge } from '../components/ui/Badge'
import { Button, LinkButton } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  fetchDriver,
  fetchDriverPeriods,
  fetchFinancialSummary,
} from '../lib/api'
import { formatJalaliLong, formatJalaliShort, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { Driver } from '../types/driver'

export function DriverFinancialPage() {
  const { user } = useAuth()
  const canManage = Boolean(user?.is_staff || user?.is_superuser)
  const { id } = useParams()
  const driverId = Number(id)
  const [driver, setDriver] = useState<Driver | null>(null)
  const [summary, setSummary] = useState<any>(null)
  const [periods, setPeriods] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { notify } = useToast()
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (!Number.isInteger(driverId) || driverId <= 0) {
      setError('شناسه راننده معتبر نیست.')
      setLoading(false)
      return
    }

    let active = true
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    Promise.all([
      fetchDriver(driverId, controller.signal),
      fetchFinancialSummary(driverId, undefined, controller.signal),
      fetchDriverPeriods(driverId, controller.signal),
    ])
      .then(([drv, sum, per]) => {
        if (active) {
          setDriver(drv)
          setSummary(sum)
          setPeriods(per)
        }
      })
      .catch((cause) => {
        if (active && !isAbortError(cause)) {
          setError(getErrorMessage(cause))
          notify('error', getErrorMessage(cause))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [driverId, reloadKey, notify])

  const handleReload = () => setReloadKey((k) => k + 1)

  if (loading) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm">
        <div className="size-7 animate-spin rounded-full border-4 border-slate-200 border-t-slate-900" />
        <p className="text-sm">در حال دریافت اطلاعات مالی راننده…</p>
      </div>
    )
  }

  if (error || !driver || !summary || !periods) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <div className="size-8 animate-spin rounded-full border-4 border-rose-200 border-t-rose-600" />
        <p className="text-sm text-rose-700">
          {error ?? 'اطلاعات مالی یافت نشد.'}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleReload}
            icon={<RefreshIcon className="size-4" />}
          >
            تلاش دوباره
          </Button>
          <Link
            to="/drivers"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-600 transition hover:bg-white/60"
          >
            <ArrowRightIcon className="size-4" />
            بازگشت به فهرست
          </Link>
        </div>
      </div>
    )
  }

  const periodsList = periods.periods || []
  const currentPeriod = periodsList.find(
    (p: any) => new Date(p.start) <= new Date() && new Date(p.end) >= new Date(),
  )


  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/drivers"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition hover:text-slate-900"
        >
          <ArrowRightIcon className="size-4" />
          بازگشت به فهرست رانندگان
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/drivers/${driver.id}`}
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
          >
            <CalendarIcon className="size-4" />
            مشاهده پروفایل
          </Link>
          {canManage && (
            <LinkButton
              to={`/financial/payments/new?driver_id=${driver.id}`}
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
              icon={<CreditCardIcon className="size-4" />}
            >
              ثبت پرداخت
            </LinkButton>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <p>{error}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleReload}
            icon={<RefreshIcon className="size-4" />}
          >
            تلاش دوباره
          </Button>
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-500">بدهی فعلی دوره</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900" dir="ltr">
            {toPersianDigits(summary.current_obligation)} AFN
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-500">بدهی معوق</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-rose-600" dir="ltr">
            {toPersianDigits(summary.overdue_debt)} AFN
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-500">اعتبار قابل استفاده</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-brand-600" dir="ltr">
            {toPersianDigits(summary.available_credit)} AFN
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-500">مجموع بدهی</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900" dir="ltr">
            {toPersianDigits(summary.driver_total_balance)} AFN
          </p>
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">
              دوره‌های مالی
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
             {todayLabel(periodsList)}
            </p>
          </div>
          <Link
            to={`/drivers/${driver.id}/fee-start-date`}
            className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 transition hover:text-slate-900"
          >
            تغییر تاریخ شروع فیس
          </Link>
        </div>

        {periodsList.length === 0 ? (
          <EmptyState
            icon={<CalendarIcon className="size-6" />}
            title="هیچ دوره‌ای یافت نشد"
            description="دوره مالی برای این راننده تعریف نشده است."
          />
        ) : (
          <div className="overflow-x-auto p-5">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2.5 text-right font-medium">دوره</th>
                  <th className="px-5 py-2.5 text-right font-medium">شروع</th>
                  <th className="px-5 py-2.5 text-right font-medium">پایان (سررسید)</th>
                  <th className="px-5 py-2.5 text-right font-medium" dir="ltr">فیس</th>
                  <th className="px-5 py-2.5 text-right font-medium" dir="ltr">تسویه نقدی</th>
                  <th className="px-5 py-2.5 text-right font-medium" dir="ltr">تسویه اعتباری</th>
                  <th className="px-5 py-2.5 text-right font-medium" dir="ltr">مانده بدهی</th>
                  <th className="px-5 py-2.5 text-right font-medium">وضعیت</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {periodsList.map((p: any, idx: number) => {
                  const isCurrent = currentPeriod?.start === p.start && currentPeriod?.end === p.end
                  const isOverdue = p.is_overdue && parseFloat(p.balance) > 0
                  return (
                    <tr
                      key={idx}
                      className={`
                        transition hover:bg-slate-50/70
                        ${isCurrent ? 'bg-slate-50' : ''}
                        ${isOverdue ? 'bg-rose-50' : ''}
                      `}
                    >
                      <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                        #{idx + 1}
                      </td>
                      <td className="px-5 py-3 text-xs text-slate-600">
                        {formatJalaliShort(p.start)}
                      </td>
                      <td className="px-5 py-3 text-xs text-slate-600">
                        {formatJalaliShort(p.end)}
                      </td>
                      <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                        {toPersianDigits(p.fee)} AFN
                      </td>
                      <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                        {toPersianDigits(p.cash_settled)} AFN
                      </td>
                      <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                        {toPersianDigits(p.credit_settled)} AFN
                      </td>
                      <td className="px-5 py-3 font-mono text-xs font-bold" dir="ltr" style={{ color: isOverdue ? '#dc2626' : '#111827' }}>
                        {toPersianDigits(p.balance)} AFN
                      </td>
                      <td className="px-5 py-3">
                        {isOverdue ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-600">
                            معوق
                          </span>
                        ) : parseFloat(p.balance) === 0 ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600">
                            تسویه‌شده
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-600">
                            남은
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">
              оборот نقدی
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              کل مبالغ نقدی دریافتی از این راننده.
            </p>
          </div>
        </div>
        <div className="overflow-x-auto p-5">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-5 py-2.5 text-right font-middle">مبلغ</th>
                <th className="px-5 py-2.5 text-right font-middle">تاریخ دریافت</th>
                <th className="px-5 py-2.5 text-right font-middle">دوره هدف</th>
                <th className="px-5 py-2.5 text-right font-middle">وضعیت</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr className="transition hover:bg-slate-50/70">
                <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                  {toPersianDigits(summary.cash_received)} AFN
                </td>
                <td className="px-5 py-3 text-xs text-slate-500">
                  {formatJalaliLong(driver.registration_date)}
                </td>
                <td className="px-5 py-3 text-xs text-slate-500">
                  {formatJalaliShort(driver.fee_start_date)}
                </td>
                <td className="px-5 py-3">
                  <StatusBadge active={driver.status} />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function todayLabel(periods: any[]): string {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const current = periods.find(
    (p: any) => new Date(p.start) <= today && new Date(p.end) >= today,
  )
  if (current) {
    return `دوره جاری: ${formatJalaliShort(current.start)} تا ${formatJalaliShort(current.end)}`
  }
  const upcoming = periods.find((p: any) => new Date(p.start) > today)
  if (upcoming) {
    return `دوره آینده آغاز می‌شود در ${formatJalaliShort(upcoming.start)}`
  }
  return 'هیچ دوره فعال یا آینده‌ای یافت نشد.'
}