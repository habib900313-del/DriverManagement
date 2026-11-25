import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { DriverAvatar } from '../components/DriverAvatar'
import {
  EyeIcon,
  ArchiveIcon,
  PencilIcon,
  PlusIcon,
  PowerIcon,
  RefreshIcon,
  SearchIcon,
  UsersIcon,
  XIcon,
} from '../components/icons'
import { StatusBadge } from '../components/ui/Badge'
import { Button, LinkButton } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { PageHeader } from '../components/ui/PageHeader'
import { Pagination } from '../components/ui/Pagination'
import { Spinner } from '../components/ui/Spinner'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { archiveDriver, fetchDrivers, fetchFinancialSummary, setDriverStatus } from '../lib/api'
import { cn } from '../lib/cn'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import {
  DRIVER_FINANCIAL_STATUS_STYLES,
  getDriverFinancialStatus,
  getDriverFinancialStatusLabel,
  parseMoney,
} from '../lib/driverFinancialStatus'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { Driver, PaginatedResponse } from '../types/driver'
import type { DriverFinancialSummary } from '../types/financial'

const PAGE_SIZE = 10

type StatusFilter = '' | 'active' | 'inactive'
type SerialOrder = 'asc' | 'desc'

const statusOptions: Array<{ value: StatusFilter; label: string }> = [
  { value: '', label: 'همه' },
  { value: 'active', label: 'فعال' },
  { value: 'inactive', label: 'غیرفعال' },
]

const serialOrderOptions: Array<{ value: SerialOrder; label: string }> = [
  { value: 'asc', label: 'صعودی' },
  { value: 'desc', label: 'نزولی' },
]

const FINANCIAL_STATUS_ORDER = ['overdue', 'debtor', 'paid', 'unknown'] as const

function FinancialStatusCell({
  summary,
  loading,
}: {
  summary?: DriverFinancialSummary
  loading: boolean
}) {
  if (loading) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-400">
        <Spinner className="size-3.5" />
        در حال محاسبه…
      </span>
    )
  }

  if (!summary) {
    return <span className="text-[11px] text-slate-400">نامشخص</span>
  }

  const status = getDriverFinancialStatus(summary)
  const style = DRIVER_FINANCIAL_STATUS_STYLES[status]
  const label = getDriverFinancialStatusLabel(summary)
  const availableCredit = parseMoney(summary.available_credit)

  return (
    <div
      className="flex flex-col items-start gap-1"
      title={[
        `بدهی معوق: ${toPersianDigits(summary.overdue_debt)} AFN`,
        `مانده دوره جاری: ${toPersianDigits(summary.current_obligation)} AFN`,
        `مانده کل: ${toPersianDigits(summary.driver_total_balance)} AFN`,
      ].join(' — ')}
    >
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium',
          style.badge,
        )}
      >
        <span
          className={cn('size-1.5 rounded-full', style.dot)}
          aria-hidden="true"
        />
        {label}
      </span>
      {status === 'unknown' ? (
        <span className="text-[11px] text-slate-500">
          اطلاعات مالی معتبر در دسترس نیست
        </span>
      ) : status === 'paid' ? (
        availableCredit !== null && availableCredit > 0 ? (
          <span className="text-[11px] text-emerald-700">
            اعتبار: {toPersianDigits(summary.available_credit)} AFN
          </span>
        ) : (
          <span className="text-[11px] text-slate-400">بدون بدهی</span>
        )
      ) : (
        <span className="font-mono text-[11px] text-slate-500" dir="ltr">
          {toPersianDigits(summary.driver_total_balance)} AFN
        </span>
      )}
    </div>
  )
}

export function DriversListPage() {
  const { user } = useAuth()
  const canManage = Boolean(user?.is_staff || user?.is_superuser)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('')
  const [serialOrder, setSerialOrder] = useState<SerialOrder>('asc')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<PaginatedResponse<Driver> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [summaries, setSummaries] = useState<
    Record<number, DriverFinancialSummary>
  >({})
  const [summariesLoading, setSummariesLoading] = useState(false)
  const { notify } = useToast()

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim())
    }, 350)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  useEffect(() => {
    setPage(1)
  }, [search, status])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    fetchDrivers(
      {
        search,
        status,
        serial_order: serialOrder,
        page,
        page_size: PAGE_SIZE,
      },
      controller.signal,
    )
      .then((response) => {
        if (!active) return
        const totalPages = Math.max(1, Math.ceil(response.count / PAGE_SIZE))
        if (page > totalPages) {
          setSummariesLoading(false)
          setPage(totalPages)
          return
        }
        setData(response)

        const ids = response.results.map((driver) => driver.id)
        if (ids.length === 0) {
          setSummariesLoading(false)
          return
        }
        setSummariesLoading(true)
        Promise.all(
          ids.map((id) =>
            fetchFinancialSummary(id, undefined, controller.signal)
              .then((summary) => [id, summary] as const)
              .catch(() => null),
          ),
        )
          .then((rows) => {
            if (!active || controller.signal.aborted) return
            setSummaries((current) => {
              const next = { ...current }
              for (const row of rows) {
                if (row) next[row[0]] = row[1]
              }
              return next
            })
          })
          .finally(() => {
            if (active && !controller.signal.aborted) {
              setSummariesLoading(false)
            }
          })
      })
      .catch((cause) => {
        if (active && !isAbortError(cause)) {
          setError(getErrorMessage(cause))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [search, status, serialOrder, page, reloadKey])

  const handleToggle = async (driver: Driver) => {
    if (busyId !== null) return
    setBusyId(driver.id)
    try {
      const updated = await setDriverStatus(driver.id, !driver.status)
      setData((current) =>
        current
          ? {
              ...current,
              results: current.results.map((item) =>
                item.id === updated.id
                  ? {
                      ...item,
                      status: updated.status,
                      status_label: updated.status_label,
                    }
                  : item,
              ),
            }
          : current,
      )
      notify(
        'success',
        updated.status
          ? `راننده «${updated.full_name}» فعال شد.`
          : `راننده «${updated.full_name}» غیرفعال شد.`,
      )
      if (status !== '') {
        // The updated row may no longer match the active status filter.
        setReloadKey((current) => current + 1)
      }
    } catch (cause) {
      notify('error', getErrorMessage(cause))
    } finally {
      setBusyId(null)
    }
  }

  const handleArchive = async (driver: Driver) => {
    if (busyId !== null) return
    const confirmed = window.confirm(
      `راننده «${driver.full_name}» با شماره مسلسل ${driver.driver_code} آرشیف شود؟`,
    )
    if (!confirmed) return

    setBusyId(driver.id)
    try {
      await archiveDriver(driver.id)
      notify('success', `راننده «${driver.full_name}» آرشیف شد.`)
      setReloadKey((current) => current + 1)
    } catch (cause) {
      notify('error', getErrorMessage(cause))
    } finally {
      setBusyId(null)
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1
  const hasFilters = Boolean(search) || status !== ''

  return (
    <div className="space-y-5">
      <PageHeader
        title="فهرست رانندگان"
        description="جستجو و مدیریت رانندگان ثبت‌شده. جستجو در سرور انجام می‌شود و شامل نام، پلیت و شماره مسلسل است."
        actions={canManage ? (
          <LinkButton
            to="/drivers/new"
            icon={<PlusIcon className="size-4" />}
          >
            ثبت راننده جدید
          </LinkButton>
        ) : undefined}
      />

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="relative w-full max-w-md">
            <SearchIcon className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="جستجو بر اساس نام، پلیت یا شماره مسلسل…"
              aria-label="جستجوی رانندگان"
              className="h-10 w-full rounded-xl border border-slate-300 bg-white pe-9 ps-10 text-sm text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => setSearchInput('')}
                className="absolute end-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
                aria-label="پاک کردن جستجو"
              >
                <XIcon className="size-4" />
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex items-center gap-2 text-xs">
              <span className="text-slate-500">ترتیب شماره مسلسل:</span>
              <div
                role="group"
                aria-label="ترتیب شماره مسلسل"
                className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5"
              >
                {serialOrderOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    aria-pressed={serialOrder === option.value}
                    onClick={() => {
                      if (serialOrder === option.value) return
                      setPage(1)
                      setSerialOrder(option.value)
                    }}
                    className={cn(
                      'rounded-md px-3 py-1.5 font-medium transition',
                      serialOrder === option.value
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-500 hover:text-slate-700',
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 text-xs">
              {statusOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setStatus(option.value)}
                  className={cn(
                    'rounded-md px-3 py-1.5 font-medium transition',
                    status === option.value
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-500 hover:text-slate-700',
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          {loading ? (
            <span className="inline-flex items-center gap-1.5">
              <Spinner className="size-3.5" />
              در حال دریافت فهرست…
            </span>
          ) : (
            <span>
              {data ? toPersianDigits(data.count) : '۰'} راننده یافت شد
              {hasFilters ? ' (با فیلترهای فعلی)' : ''}
            </span>
          )}
          {hasFilters && (
            <button
              type="button"
              onClick={() => {
                setSearchInput('')
                setSearch('')
                setStatus('')
              }}
              className="font-medium text-slate-700 underline-offset-2 hover:underline"
            >
              حذف فیلترها
            </button>
          )}
        </div>

        <div
          className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-slate-100 pt-3 text-[11px] text-slate-600"
          aria-label="راهنمای رنگ‌بندی وضعیت مالی"
        >
          <span className="font-medium text-slate-700">
            راهنمای وضعیت مالی:
          </span>
          {FINANCIAL_STATUS_ORDER.map((status) => {
            const style = DRIVER_FINANCIAL_STATUS_STYLES[status]
            return (
              <span
                key={status}
                className="inline-flex items-center gap-1.5"
                title={style.description}
              >
                <span
                  className={cn('size-2 rounded-full', style.dot)}
                  aria-hidden="true"
                />
                {style.legend}
              </span>
            )
          })}
        </div>
      </div>

      {error ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 px-6 py-12 text-center">
          <p className="text-sm text-rose-700">{error}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setReloadKey((current) => current + 1)}
            icon={<RefreshIcon className="size-4" />}
          >
            تلاش دوباره
          </Button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead className="border-b border-slate-200 bg-slate-50/70 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3 text-right font-medium">
                    شماره مسلسل
                  </th>
                  <th className="px-4 py-3 text-right font-medium">نام راننده</th>
                  <th className="px-4 py-3 text-right font-medium">پلیت موتر</th>
                  <th className="px-4 py-3 text-right font-medium">تاریخ ثبت</th>
                  <th className="px-4 py-3 text-right font-medium">وضعیت</th>
                  <th className="px-4 py-3 text-right font-medium">
                    وضعیت مالی
                  </th>
                  <th className="px-4 py-3 text-left font-medium">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading
                  ? Array.from({ length: 6 }, (_, index) => (
                      <tr key={`skeleton-${index}`} className="animate-pulse">
                        <td className="px-4 py-3.5">
                          <div className="h-4 w-20 rounded bg-slate-100" />
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex items-center gap-3">
                            <div className="size-9 rounded-full bg-slate-100" />
                            <div className="h-4 w-32 rounded bg-slate-100" />
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="h-4 w-24 rounded bg-slate-100" />
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="h-4 w-24 rounded bg-slate-100" />
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="h-6 w-16 rounded-full bg-slate-100" />
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="h-6 w-24 rounded-full bg-slate-100" />
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="ms-auto h-8 w-24 rounded-lg bg-slate-100" />
                        </td>
                      </tr>
                    ))
                  : data?.results.map((driver) => {
                      const summary = summaries[driver.id]
                      const financialStatus = summary
                        ? getDriverFinancialStatus(summary)
                        : null
                      return (
                        <tr
                          key={driver.id}
                          className={cn(
                            'transition',
                            financialStatus
                              ? DRIVER_FINANCIAL_STATUS_STYLES[financialStatus]
                                  .row
                              : 'hover:bg-slate-50/70',
                          )}
                        >
                        <td className="px-4 py-3">
                          <Link
                            to={`/drivers/${driver.id}`}
                            className="font-mono text-xs font-medium text-slate-700 hover:text-slate-950"
                            dir="ltr"
                          >
                            {driver.driver_code}
                          </Link>
                        </td>
                        <td className="px-4 py-3">
                          <Link
                            to={`/drivers/${driver.id}`}
                            className="flex items-center gap-3"
                          >
                            <DriverAvatar
                              src={driver.photo_url}
                              name={driver.full_name}
                              className="size-9 rounded-full text-xs"
                            />
                            <span className="font-medium text-slate-800 hover:text-slate-950">
                              {driver.full_name}
                            </span>
                          </Link>
                        </td>
                        <td className="px-4 py-3">
                          <Link
                            to={`/drivers/${driver.id}`}
                            className="font-mono text-xs text-slate-600 hover:text-slate-900"
                            dir="ltr"
                          >
                            {driver.plate_number}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500">
                          {formatJalaliShort(driver.registration_date)}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge active={driver.status} />
                        </td>
                        <td className="px-4 py-3">
                          <FinancialStatusCell
                            summary={summary}
                            loading={summariesLoading && !summary}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1">
                            <Link
                              to={`/drivers/${driver.id}`}
                              className="inline-flex size-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                              aria-label={`مشاهده پروفایل ${driver.full_name}`}
                              title="مشاهده پروفایل"
                            >
                              <EyeIcon className="size-4" />
                            </Link>
                            {canManage && (
                              <>
                                <Link
                                  to={`/drivers/${driver.id}/edit`}
                                  className="inline-flex size-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                                  aria-label={`ویرایش ${driver.full_name}`}
                                  title="ویرایش"
                                >
                                  <PencilIcon className="size-4" />
                                </Link>
                                <button
                                  type="button"
                                  onClick={() => handleToggle(driver)}
                                  disabled={busyId !== null}
                                  className={cn(
                                    'inline-flex size-8 items-center justify-center rounded-lg transition disabled:opacity-40',
                                    driver.status
                                      ? 'text-amber-600 hover:bg-amber-50'
                                      : 'text-emerald-600 hover:bg-emerald-50',
                                  )}
                                  aria-label={
                                    driver.status
                                      ? `غیرفعال کردن ${driver.full_name}`
                                      : `فعال کردن ${driver.full_name}`
                                  }
                                  title={
                                    driver.status
                                      ? 'غیرفعال کردن راننده'
                                      : 'فعال کردن راننده'
                                  }
                                >
                                  {busyId === driver.id ? (
                                    <Spinner className="size-4" />
                                  ) : (
                                    <PowerIcon className="size-4" />
                                  )}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleArchive(driver)}
                                  disabled={busyId !== null}
                                  className="inline-flex size-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-rose-700 disabled:opacity-40"
                                  aria-label={`آرشیف کردن ${driver.full_name}`}
                                  title="آرشیف راننده"
                                >
                                  {busyId === driver.id ? (
                                    <Spinner className="size-4" />
                                  ) : (
                                    <ArchiveIcon className="size-4" />
                                  )}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                      )
                    })}
              </tbody>
            </table>
          </div>

          {!loading && data && data.results.length === 0 && (
            <EmptyState
              icon={<UsersIcon className="size-6" />}
              title={
                hasFilters
                  ? 'راننده‌ای با این مشخصات یافت نشد'
                  : 'هنوز راننده‌ای ثبت نشده است'
              }
              description={
                hasFilters
                  ? 'عبارت جستجو یا فیلتر وضعیت را تغییر دهید.'
                  : 'برای شروع، اولین راننده را با شماره مسلسل دستی ثبت کنید.'
              }
              action={
                hasFilters ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setSearchInput('')
                      setSearch('')
                      setStatus('')
                    }}
                  >
                    حذف فیلترها
                  </Button>
                ) : canManage ? (
                  <LinkButton
                    to="/drivers/new"
                    size="sm"
                    icon={<PlusIcon className="size-4" />}
                  >
                    ثبت اولین راننده
                  </LinkButton>
                ) : undefined
              }
            />
          )}

          {!loading && data && data.results.length > 0 && (
            <Pagination
              page={page}
              totalPages={totalPages}
              totalItems={data.count}
              onChange={setPage}
            />
          )}
        </div>
      )}
    </div>
  )
}
