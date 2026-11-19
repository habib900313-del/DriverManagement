import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  CalendarIcon,
  RefreshIcon,
  SearchIcon,
} from '../components/icons'
import { Button } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { Pagination } from '../components/ui/Pagination'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { deletePayment, fetchPayments } from '../lib/api'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import { applyListChange, DEFAULT_PAGE_SIZE, pageAfterDeletion } from '../lib/pagination'
import type { PaymentListItem, PaymentListParams } from '../types/financial'

const ALLOCATION_TYPE_LABELS: Record<string, string> = {
  fee_period: 'تسویه فیس دوره',
  credit: 'اعتبار',
}

function statusLabel(value: string): string {
  switch (value) {
    case 'received':
      return 'دریافت‌شده'
    case 'voided':
      return 'ابطال‌شده'
    case 'corrected':
      return 'اصلاح‌شده'
    default:
      return value
  }
}

function statusClass(value: string): string {
  switch (value) {
    case 'received':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700'
    case 'voided':
      return 'border-rose-200 bg-rose-50 text-rose-700'
    case 'corrected':
      return 'border-brand-200 bg-brand-50 text-brand-700'
    default:
      return 'border-slate-200 bg-slate-100 text-slate-600'
  }
}

export function FinancialHistoryPage() {
  const { notify } = useToast()
  const { user } = useAuth()
  const canDelete = Boolean(user?.is_staff || user?.is_superuser)
  const [searchParams, setSearchParams] = useSearchParams()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [payments, setPayments] = useState<PaymentListItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [deletingPayment, setDeletingPayment] = useState<PaymentListItem | null>(null)
  const [deleting, setDeleting] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  const [filters, setFilters] = useState<PaymentListParams>(() => {
    const driverId = searchParams.get('driver_id')
    const dateFrom = searchParams.get('date_from')
    const dateTo = searchParams.get('date_to')
    const search = searchParams.get('search')
    return {
      driver_id: driverId ? Number(driverId) : undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      search: search || undefined,
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
    }
  })

  const load = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setError(null)

    try {
      const response = await fetchPayments(filters, controller.signal)
      setPayments(response.results)
      setTotalCount(response.count)
    } catch (cause) {
      if (isAbortError(cause)) return
      const msg = getErrorMessage(cause)
      setError(msg)
      notify('error', msg)
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false)
      }
    }
  }, [filters, notify])

  useEffect(() => {
    load()
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [load])

  const handleFilterChange = (next: Partial<PaymentListParams>) => {
    const updated = applyListChange(filters, next)
    setFilters(updated)
    const params = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(updated)) {
      if (value === undefined || value === null || value === '') {
        params.delete(key)
      } else {
        params.set(key, String(value))
      }
    }
    setSearchParams(params)
  }

  const handleDelete = async () => {
    if (!deletingPayment || deleting) return
    const target = deletingPayment
    setDeleting(true)
    try {
      await deletePayment(target.id)
      notify('success', 'پرداخت با موفقیت حذف شد.')
      setDeletingPayment(null)
      const page = filters.page ?? 1
      const nextPage = pageAfterDeletion(page, payments.length)
      if (nextPage !== page) {
        handleFilterChange({ page: nextPage })
      } else {
        await load()
      }
    } catch (cause) {
      notify('error', getErrorMessage(cause))
    } finally {
      setDeleting(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(totalCount / (filters.page_size ?? DEFAULT_PAGE_SIZE)))

  const activeFilters = useMemo(() => {
    const items: Array<{ label: string; value: string }> = []
    if (filters.driver_id) items.push({ label: 'راننده', value: String(filters.driver_id) })
    if (filters.date_from) items.push({ label: 'از تاریخ', value: filters.date_from })
    if (filters.date_to) items.push({ label: 'تا تاریخ', value: filters.date_to })
    if (filters.search) items.push({ label: 'جستجو', value: filters.search })
    return items
  }, [filters])

  if (loading) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm">
        <div className="size-7 animate-spin rounded-full border-4 border-slate-200 border-t-slate-900" />
        <p className="text-sm">در حال دریافت سوابق پرداخت…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <div className="size-8 animate-spin rounded-full border-4 border-rose-200 border-t-rose-600" />
        <p className="text-sm text-rose-700">{error}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={load}
            icon={<RefreshIcon className="size-4" />}
          >
            تلاش دوباره
          </Button>
          <Link
            to="/financial"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-600 transition hover:bg-white/60"
          >
            <ArrowRightIcon className="size-4" />
            بازگشت به داشبورد مالی
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <Link
          to="/financial"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition hover:text-slate-900"
        >
          <ArrowRightIcon className="size-4" />
          بازگشت به داشبورد مالی
        </Link>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <p>{error}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={load}
            icon={<RefreshIcon className="size-4" />}
          >
            تلاش دوباره
          </Button>
        </div>
      )}

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">سوابق پرداخت</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              لیست پرداخت‌های ثبت‌شده در سیستم.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <CalendarIcon className="size-4" />
              <input
                type="date"
                defaultValue={filters.date_from ?? ''}
                onChange={(e) =>
                  handleFilterChange({ date_from: e.target.value || undefined })
                }
                className="rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-xs outline-none transition hover:border-slate-300 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
              />
              <span className="text-xs text-slate-400">تا</span>
              <input
                type="date"
                defaultValue={filters.date_to ?? ''}
                onChange={(e) =>
                  handleFilterChange({ date_to: e.target.value || undefined })
                }
                className="rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-xs outline-none transition hover:border-slate-300 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
              />
            </div>
            <div className="relative">
              <SearchIcon className="absolute left-2.5 top-2.5 size-4 text-slate-400" />
              <input
                type="text"
                defaultValue={filters.search ?? ''}
                placeholder="جستجو در کد راننده، نام، شماره رسید…"
                onChange={(e) =>
                  handleFilterChange({ search: e.target.value || undefined })
                }
                className="w-64 rounded-xl border border-slate-200 bg-white py-1.5 pl-9 pr-2.5 text-xs text-slate-900 shadow-xs outline-none transition hover:border-slate-300 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
              />
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setFilters({ driver_id: undefined, date_from: undefined, date_to: undefined, search: undefined, page: 1, page_size: DEFAULT_PAGE_SIZE })
                setSearchParams(new URLSearchParams())
              }}
              disabled={activeFilters.length === 0}
            >
              حذف فیلترها
            </Button>
          </div>
        </div>

        {activeFilters.length > 0 && (
          <div className="flex flex-wrap gap-2 px-5 py-3">
            {activeFilters.map((f, idx) => (
              <span key={idx} className="inline-flex items-center gap-1.5 rounded-full border border-brand-100 bg-brand-50 px-2.5 py-1 text-xs text-brand-700">
                <span className="font-medium">{f.label}:</span> {f.value}
              </span>
            ))}
          </div>
        )}

        {payments.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <EmptyState
              icon={<CalendarIcon className="size-6" />}
              title="هیچ سابقه پرداختی ثبت نشده است"
              description={
                totalCount === 0
                  ? 'هیچ پرداختی با فیلترهای انتخاب شده یافت نشد.'
                  : 'در صفحه فعلی پایل جزئیات برای نمایش وجود ندارد.'
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto p-5">
            <table className="w-full min-w-[980px] text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2.5 text-right font-medium">راننده</th>
                  <th className="px-5 py-2.5 text-right font-middle" dir="ltr">مبلغ (AFN)</th>
                  <th className="px-5 py-2.5 text-right font-middle">تاریخ پرداخت</th>
                  <th className="px-5 py-2.5 text-right font-middle">وضعیت</th>
                  <th className="px-5 py-2.5 text-right font-middle" dir="ltr">شماره رسید</th>
                  <th className="px-5 py-2.5 text-left text-sm text-slate-500">تخصیص به دوره</th>
                  <th className="px-5 py-2.5 text-left text-sm text-slate-500">جزئیات</th>
                  <th className="px-5 py-2.5 text-left text-sm text-slate-500">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {payments.map((p) => {
                  const activeAllocs = p.allocations.filter((a) => !a.is_reversed)
                  return (
                    <tr key={p.id} className="transition hover:bg-slate-50/70">
                      <td className="px-5 py-3 text-xs text-slate-600">
                        <div className="font-medium">{p.driver_code}</div>
                        <div className="text-slate-500">{p.driver_name}</div>
                      </td>
                      <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                        {toPersianDigits(p.amount)} AFN
                      </td>
                      <td className="px-5 py-3 text-xs text-slate-600">
                        {formatJalaliShort(p.payment_date)}
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${statusClass(p.status)}`}
                        >
                          <span
                            className={`size-1.5 rounded-full ${p.status === 'received' ? 'bg-emerald-500' : p.status === 'voided' ? 'bg-rose-500' : 'bg-brand-500'}`}
                          />
                          {statusLabel(p.status)}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-xs text-slate-600" dir="ltr">
                        {p.receipt_number || '—'}
                      </td>
                      <td className="px-5 py-3 text-left text-xs text-slate-500">
                        {activeAllocs.length === 0 ? (
                          <span>بدون تخصیص</span>
                        ) : (
                          <div className="space-y-1">
                            {activeAllocs.map((a) => (
                              <div key={a.id} className="text-slate-600">
                                {a.target_period_start && a.target_period_end ? (
                                  <>
                                    {formatJalaliShort(a.target_period_start)} تا {formatJalaliShort(a.target_period_end)}
                                    {a.allocated_amount ? (
                                      <span className="ml-1 font-mono">({toPersianDigits(a.allocated_amount)} AFN)</span>
                                    ) : null}
                                  </>
                                ) : (
                                  <>
                                    {ALLOCATION_TYPE_LABELS[a.allocation_type] ?? a.allocation_type}
                                    {a.allocated_amount ? (
                                      <span className="ml-1 font-mono">({toPersianDigits(a.allocated_amount)} AFN)</span>
                                    ) : null}
                                  </>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-5 py-3 text-left">
                        <Link
                          to={`/financial/payments/${p.id}`}
                          className="text-xs font-medium text-brand-700 hover:text-brand-900"
                        >
                          مشاهده / اصلاح
                        </Link>
                      </td>
                      <td className="px-5 py-3 text-left">
                        {canDelete && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                            onClick={() => setDeletingPayment(p)}
                          >
                            حذف
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={filters.page ?? 1}
          totalPages={totalPages}
          totalItems={totalCount}
          onChange={(nextPage) => {
            handleFilterChange({ page: nextPage })
          }}
        />
      </section>

      {deletingPayment && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-payment-title"
          onClick={() => {
            if (!deleting) setDeletingPayment(null)
          }}
        >
          <div
            className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl"
            dir="rtl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-rose-50 text-rose-600">
                <AlertTriangleIcon className="size-5" />
              </div>
              <div>
                <h2
                  id="delete-payment-title"
                  className="text-sm font-semibold text-slate-900"
                >
                  حذف دائمی پرداخت
                </h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  این عملیات بازگشت‌ناپذیر است. پرداخت و تخصیص‌های مرتبط با آن از
                  همه فهرست‌ها و گزارش‌ها حذف می‌شوند.
                </p>
              </div>
            </div>

            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 rounded-xl bg-slate-50 px-3.5 py-3 text-xs">
              <div>
                <dt className="text-slate-400">راننده</dt>
                <dd className="mt-0.5 font-medium text-slate-700">
                  {deletingPayment.driver_code} — {deletingPayment.driver_name}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">مبلغ</dt>
                <dd className="mt-0.5 font-mono font-medium text-slate-700" dir="ltr">
                  {toPersianDigits(deletingPayment.amount)} AFN
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">تاریخ پرداخت</dt>
                <dd className="mt-0.5 font-medium text-slate-700">
                  {formatJalaliShort(deletingPayment.payment_date)}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">شماره رسید</dt>
                <dd className="mt-0.5 font-medium text-slate-700" dir="ltr">
                  {deletingPayment.receipt_number || '—'}
                </dd>
              </div>
            </dl>

            <div className="mt-5 flex items-center justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDeletingPayment(null)}
                disabled={deleting}
              >
                انصراف
              </Button>
              <Button
                variant="danger"
                size="sm"
                loading={deleting}
                onClick={handleDelete}
              >
                حذف دائمی
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
