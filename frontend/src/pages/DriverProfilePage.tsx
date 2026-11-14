import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DriverAvatar } from '../components/DriverAvatar'
import { DriverPeriodPayments } from '../components/DriverPeriodPayments'
import {
  AlertCircleIcon,
  ArrowRightIcon,
  CalendarIcon,
  CarIcon,
  CheckCircleIcon,
  CreditCardIcon,
  MapPinIcon,
  PencilIcon,
  PhoneIcon,
  PowerIcon,
  RefreshIcon,
  UserIcon,
  UsersIcon,
  XCircleIcon,
} from '../components/icons'
import { StatusBadge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { useToast } from '../context/ToastContext'
import {
  fetchDriver,
  fetchFinancialSummary,
  fetchDriverPeriodCoverage,
  setDriverStatus,
} from '../lib/api'
import { cn } from '../lib/cn'
import {
  formatGregorianShort,
  formatJalaliLong,
  formatJalaliShort,
  formatKabulDateTime,
  toPersianDigits,
} from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { Driver } from '../types/driver'
import type { DriverPeriodCoverage } from '../types/financial'

function InfoRow({
  label,
  icon,
  children,
  dir,
}: {
  label: string
  icon?: ReactNode
  children: ReactNode
  dir?: 'ltr' | 'rtl'
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 py-2.5 last:border-0">
      <dt className="flex shrink-0 items-center gap-2 text-xs text-slate-500">
        {icon}
        {label}
      </dt>
      <dd
        className="min-w-0 text-left text-sm font-medium text-slate-800"
        dir={dir}
      >
        {children}
      </dd>
    </div>
  )
}

function InfoCard({
  title,
  children,
  className,
}: {
  title: string
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={cn(
        'rounded-xl border border-slate-200 bg-white p-4 shadow-sm',
        className,
      )}
    >
      <h2 className="mb-1 text-sm font-semibold text-slate-800">{title}</h2>
      <dl>{children}</dl>
    </section>
  )
}

function DateValue({ iso }: { iso: string }) {
  return (
    <div>
      <p className="text-sm font-medium text-slate-800">{formatJalaliLong(iso)}</p>
      <p className="mt-0.5 font-mono text-[11px] text-slate-400" dir="ltr">
        {formatGregorianShort(iso)}
      </p>
    </div>
  )
}

export function DriverProfilePage() {
  const { id } = useParams()
  const driverId = Number(id)
  const [driver, setDriver] = useState<Driver | null>(null)
  const [financial, setFinancial] = useState<any>(null)
  const [periodCoverage, setPeriodCoverage] = useState<DriverPeriodCoverage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [statusBusy, setStatusBusy] = useState(false)
  const { notify } = useToast()

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
      fetchDriverPeriodCoverage(driverId, undefined, controller.signal),
    ])
      .then(([drv, financial, coverage]) => {
        if (active) {
          setDriver(drv)
          setFinancial(financial)
          setPeriodCoverage(coverage)
        }
      })
      .catch((cause) => {
        if (active && !isAbortError(cause)) setError(getErrorMessage(cause))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [driverId, reloadKey])

  const handleToggle = async () => {
    if (!driver || statusBusy) return
    setStatusBusy(true)
    try {
      const updated = await setDriverStatus(driver.id, !driver.status)
      setDriver(updated)
      notify(
        'success',
        updated.status
          ? 'راننده با موفقیت فعال شد.'
          : 'راننده با موفقیت غیرفعال شد.',
      )
    } catch (cause) {
      notify('error', getErrorMessage(cause))
    } finally {
      setStatusBusy(false)
    }
  }

  const handleReload = () => setReloadKey((current) => current + 1)

  if (loading) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm">
        <Spinner className="size-7" />
        <p className="text-sm">در حال دریافت پروفایل راننده…</p>
      </div>
    )
  }

  if (error || !driver) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <AlertCircleIcon className="size-8 text-rose-400" />
        <p className="text-sm text-rose-700">
          {error ?? 'راننده مورد نظر یافت نشد.'}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setReloadKey((current) => current + 1)}
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Link
            to={`/drivers/${driver.id}/edit`}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
          >
            <PencilIcon className="size-4" />
            ویرایش اطلاعات
          </Link>
          <Link
            to={`/financial/payments/new?driver_id=${driver.id}`}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
          >
            <CreditCardIcon className="size-4" />
            ثبت پرداخت
          </Link>
          <Button
            variant={driver.status ? 'danger' : 'success'}
            loading={statusBusy}
            onClick={handleToggle}
            icon={<PowerIcon className="size-4" />}
          >
            {driver.status ? 'غیرفعال کردن راننده' : 'فعال کردن راننده'}
          </Button>
          <Button variant="secondary" size="sm" onClick={handleReload} icon={<RefreshIcon className="size-4" />}>
            بازخوانی
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="h-24 bg-gradient-to-l from-slate-900 via-slate-800 to-slate-700" />
        <div className="px-5 pb-6 sm:px-6">
          <div className="-mt-12 flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-wrap items-end gap-4">
              <DriverAvatar
                src={driver.photo_url}
                name={driver.full_name}
                className="size-24 rounded-2xl border-4 border-white text-2xl shadow-md"
              />
              <div className="pb-1">
                <h1 className="text-xl font-bold text-slate-900 sm:text-2xl">
                  {driver.full_name}
                </h1>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-slate-500">
                  <span className="font-mono text-xs" dir="ltr">
                    {driver.driver_code}
                  </span>
                  <span className="size-1 rounded-full bg-slate-300" />
                  <span className="font-mono text-xs" dir="ltr">
                    {driver.plate_number}
                  </span>
                  <StatusBadge active={driver.status} />
                </div>
              </div>
            </div>
          </div>

          <div
            className={cn(
              'mt-5 flex items-start gap-2 rounded-lg border px-3 py-2.5 text-xs leading-5',
              driver.status
                ? 'border-emerald-100 bg-emerald-50 text-emerald-700'
                : 'border-amber-100 bg-amber-50 text-amber-700',
            )}
          >
            {driver.status ? (
              <CheckCircleIcon className="mt-0.5 size-4 shrink-0" />
            ) : (
              <XCircleIcon className="mt-0.5 size-4 shrink-0" />
            )}
            <p>
              {driver.status
                ? 'این راننده فعال است و در فهرست رانندگان فعال نمایش داده می‌شود.'
                : 'این راننده غیرفعال است. اطلاعات او حفظ شده و سابقه حذف نشده است؛ هر زمان لازم شد می‌توانید او را فعال کنید.'}
            </p>
          </div>

          <div className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            <InfoCard title="مشخصات فردی">
              <InfoRow label="نام کامل" icon={<UserIcon className="size-4 text-slate-400" />}>
                {driver.full_name}
              </InfoRow>
              <InfoRow label="نام پدر" icon={<UsersIcon className="size-4 text-slate-400" />}>
                {driver.father_name}
              </InfoRow>
              <InfoRow
                label="شماره تذکره"
                icon={<CreditCardIcon className="size-4 text-slate-400" />}
                dir="ltr"
              >
                {driver.tazkira_number}
              </InfoRow>
            </InfoCard>

            <InfoCard title="تماس و موتر">
              <InfoRow
                label="شماره تماس"
                icon={<PhoneIcon className="size-4 text-slate-400" />}
                dir="ltr"
              >
                {driver.phone}
              </InfoRow>
              <InfoRow
                label="پلیت موتر"
                icon={<CarIcon className="size-4 text-slate-400" />}
                dir="ltr"
              >
                {driver.plate_number}
              </InfoRow>
              <InfoRow label="شماره مسلسل" dir="ltr">
                {driver.driver_code}
              </InfoRow>
            </InfoCard>

            <InfoCard title="تاریخ‌ها">
              <InfoRow
                label="تاریخ ثبت"
                icon={<CalendarIcon className="size-4 text-slate-400" />}
              >
                <DateValue iso={driver.registration_date} />
              </InfoRow>
              <InfoRow
                label="شروع فیس"
                icon={<CalendarIcon className="size-4 text-slate-400" />}
              >
                <DateValue iso={driver.fee_start_date} />
              </InfoRow>
            </InfoCard>

            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:col-span-2 xl:col-span-3">
              <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <MapPinIcon className="size-4 text-slate-400" />
                آدرس
              </h2>
              <p className="mt-2 whitespace-pre-line text-sm leading-7 text-slate-700">
                {driver.address}
              </p>
            </section>
          </div>

          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-200 pb-3">
              <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <CreditCardIcon className="size-4 text-slate-400" />
                وضعیت مالی
              </h2>
              <Link
                to={`/financial/payments/new?driver_id=${driver.id}`}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 transition hover:text-slate-900"
              >
                <ArrowRightIcon className="size-4" />
                ثبت پرداخت جدید
              </Link>
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <p className="text-xs font-medium text-slate-500">بدهی دوره جاری</p>
                <p className="mt-1 text-lg font-bold text-slate-900" dir="ltr">
                  {toPersianDigits(financial?.current_obligation || '0')} AFN
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <p className="text-xs font-medium text-slate-500">بدهی معوق</p>
                <p className="mt-1 text-lg font-bold text-rose-600" dir="ltr">
                  {toPersianDigits(financial?.overdue_debt || '0')} AFN
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <p className="text-xs font-medium text-slate-500">مجموع بدهی</p>
                <p className="mt-1 text-lg font-bold text-slate-900" dir="ltr">
                  {toPersianDigits(financial?.driver_total_balance || '0')} AFN
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <p className="text-xs font-medium text-slate-500">اعتبار موجود</p>
                <p className="mt-1 text-lg font-bold text-emerald-600" dir="ltr">
                  {toPersianDigits(financial?.available_credit || '0')} AFN
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <p className="text-xs font-medium text-slate-500">دریافت نقدی</p>
                <p className="mt-1 text-lg font-bold text-blue-600" dir="ltr">
                  {toPersianDigits(financial?.cash_received || '0')} AFN
                </p>
              </div>
            </div>
          </section>

          <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-800">
                <CalendarIcon className="size-4 text-slate-400" />
                دوره‌های مالی
              </h2>
              <Link
                to={`/financial/drivers/${driver.id}`}
                className="text-xs font-medium text-slate-600 hover:text-slate-900"
              >
                نمایش همه »</Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="bg-slate-50 text-xs text-slate-500">
                  <tr>
                    <th className="px-4 py-2 text-right font-medium">دوره</th>
                    <th className="px-4 py-2 text-right font-middle">شروع</th>
                    <th className="px-4 py-2 text-right font-middle">پایان</th>
                    <th className="px-4 py-2 text-right font-middle" dir="ltr">بدهی</th>
                    <th className="px-4 py-2 text-right font-middle" dir="ltr">وضعیت</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(financial?.periods || []).map((p: any, idx: number) => {
                    const isOverdue = p.is_overdue && parseFloat(p.balance) > 0
                    return (
                      <tr key={idx} className={`transition hover:bg-slate-50/70 ${isOverdue ? 'bg-rose-50' : ''}`}>
                        <td className="px-4 py-2 text-sm font-mono text-slate-600" dir="ltr">
                          #{idx + 1}
                        </td>
                        <td className="px-4 py-2 text-xs text-slate-500">
                          {formatJalaliShort(p.start)}
                        </td>
                        <td className="px-4 py-2 text-xs text-slate-500">
                          {formatJalaliShort(p.end)}
                        </td>
                        <td className="px-4 py-2 font-mono text-xs text-slate-600" dir="ltr">
                          {toPersianDigits(p.balance)} AFN
                        </td>
                        <td className="px-4 py-2 text-xs">
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
                              باقی‌مانده
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <DriverPeriodPayments coverage={periodCoverage} />

          <div className="mt-6 flex flex-wrap gap-x-6 gap-y-1 border-t border-slate-100 pt-4 text-[11px] text-slate-400">
            <span>تاریخ ایجاد: {formatKabulDateTime(driver.created_at)}</span>
            <span>آخرین ویرایش: {formatKabulDateTime(driver.updated_at)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
