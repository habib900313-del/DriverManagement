import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  fetchActivityLog,
  fetchActivityLogFilters,
  fetchActivityLogs,
} from '../lib/api'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type {
  ActivityLogDetail,
  ActivityLogFilterOptions,
  ActivityLogListItem,
  ActivityLogListParams,
} from '../types/activity'
import { Button } from '../components/ui/Button'
import { Field, inputClass } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { Pagination } from '../components/ui/Pagination'
import { EmptyState } from '../components/ui/EmptyState'
import { DualDateInput } from '../components/DualDateInput'
import {
  AlertCircleIcon,
  CheckCircleIcon,
  HistoryIcon,
  SearchIcon,
  XIcon,
} from '../components/icons'
import { cn } from '../lib/cn'
import { formatJalaliShort, formatKabulDateTime, isValidIsoDate, toPersianDigits } from '../lib/dates'

const PAGE_SIZE = 25

const ACTION_LABELS: Record<string, string> = {
  login: 'ورود به سیستم',
  login_failed: 'ورود ناموفق',
  logout: 'خروج از سیستم',
  user_create: 'ایجاد کاربر',
  user_update: 'ویرایش کاربر',
  user_edit_denied: 'تلاش ناموفق برای ویرایش کاربر',
  user_password_set: 'تعیین رمز عبور جدید',
  driver_create: 'ایجاد راننده',
  driver_update: 'ویرایش راننده',
  driver_activate: 'فعال‌سازی راننده',
  driver_deactivate: 'غیرفعال‌سازی راننده',
  driver_archive: 'آرشیف راننده',
  driver_restore: 'بازگردانی راننده',
  document_upload: 'بارگذاری سند',
  document_view: 'مشاهده سند',
  document_download: 'دانلود سند',
  document_deactivate: 'غیرفعال‌سازی سند',
  payment_receive: 'ثبت پرداخت',
  credit_consume: 'مصرف اعتبار',
  payment_void: 'ابطال پرداخت',
  payment_correct: 'اصلاح پرداخت',
  allocation_correct: 'اصلاح تخصیص',
  credit_allocation_correct: 'اصلاح تخصیص اعتبار',
  waiver_create: 'ایجاد بخشودگی',
  transfer_create: 'انتقال بدهی',
  payment_refund: 'بازپرداخت (Refund)',
  adjustment_reverse: 'برگشت اصلاحیه',
  transfer_unsettle_reverse: 'بازگشایی دوره و برگشت انتقال',
  fee_start_date_change: 'تغییر تاریخ شروع فیس',
  fee_schedule_change: 'تغییر جدول فیس',
  online_payment_create: 'ثبت پرداخت آنلاین',
  online_payment_void: 'ابطال پرداخت آنلاین',
  online_payment_correct: 'اصلاح پرداخت آنلاین',
}

const MODULE_LABELS: Record<string, string> = {
  drivers: 'رانندگان',
  payments: 'عملیات مالی',
  users: 'مدیریت کاربران',
  documents: 'اسناد',
  auth: 'احراز هویت',
  other: 'سایر',
}

const FIELD_LABELS: Record<string, string> = {
  driver_code: 'کد راننده',
  full_name: 'نام کامل',
  father_name: 'نام پدر',
  phone: 'شماره تماس',
  tazkira_number: 'شماره تذکره',
  plate_number: 'شماره پلاک',
  address: 'آدرس',
  registration_date: 'تاریخ ثبت',
  fee_start_date: 'تاریخ شروع فیس',
  status: 'وضعیت',
  is_active: 'فعال بودن',
  role: 'نقش',
  username: 'نام کاربری',
  documents: 'اسناد',
  document_name: 'نام سند',
  reason: 'دلیل',
  amount: 'مبلغ',
  payment_id: 'شناسه پرداخت',
  allocation_id: 'شناسه تخصیص',
  period_start: 'شروع دوره',
  period_end: 'پایان دوره',
  driver_id: 'شناسه راننده',
  changed_fields: 'فیلدهای تغییرکرده',
  password_changed: 'رمز تغییر کرد',
}

const EMPTY_FILTERS = {
  actor: '',
  action: '',
  module: '',
  date_from: '',
  date_to: '',
  search: '',
}

type FilterState = typeof EMPTY_FILTERS

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}

function moduleLabel(module: string): string {
  return MODULE_LABELS[module] ?? module
}

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

/** Render a single stored value in a compact, human-readable form. */
function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'بله' : 'خیر'
  if (typeof value === 'number') return toPersianDigits(value)
  if (typeof value === 'string') {
    if (isValidIsoDate(value)) {
      return `${formatJalaliShort(value)} (${toPersianDigits(value)})`
    }
    return toPersianDigits(value)
  }
  if (Array.isArray(value)) {
    if (!value.length) return '—'
    return toPersianDigits(value.map((item) => renderValue(item)).join('، '))
  }
  return JSON.stringify(value)
}

function StatusPill({ status }: { status: 'success' | 'failure' }) {
  const success = status === 'success'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
        success
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-rose-200 bg-rose-50 text-rose-700',
      )}
    >
      {success ? (
        <CheckCircleIcon className="size-3.5" />
      ) : (
        <AlertCircleIcon className="size-3.5" />
      )}
      {success ? 'موفق' : 'ناموفق'}
    </span>
  )
}

function KeyValueList({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
  if (!entries.length) {
    return <p className="text-xs text-slate-400">اطلاعاتی ثبت نشده است.</p>
  }
  return (
    <dl className="divide-y divide-slate-100">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] gap-3 py-2"
        >
          <dt className="text-xs font-medium text-slate-500">{fieldLabel(key)}</dt>
          <dd className="min-w-0 break-words text-xs text-slate-800">
            {renderValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function PayloadComparison({
  before,
  after,
}: {
  before: unknown
  after: unknown
}) {
  if (!before && !after) return null

  const beforeObject = isPlainObject(before) ? before : null
  const afterObject = isPlainObject(after) ? after : null

  if (!beforeObject || !afterObject) {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <p className="mb-2 text-xs font-semibold text-slate-600">قبل از تغییر</p>
          {beforeObject ? (
            <KeyValueList data={beforeObject} />
          ) : (
            <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-[11px] text-slate-700" dir="ltr">
              {before ? JSON.stringify(before, null, 2) : '—'}
            </pre>
          )}
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <p className="mb-2 text-xs font-semibold text-slate-600">بعد از تغییر</p>
          {afterObject ? (
            <KeyValueList data={afterObject} />
          ) : (
            <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-[11px] text-slate-700" dir="ltr">
              {after ? JSON.stringify(after, null, 2) : '—'}
            </pre>
          )}
        </div>
      </div>
    )
  }

  const keys = Array.from(
    new Set([...Object.keys(beforeObject), ...Object.keys(afterObject)]),
  )

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200">
      <table className="w-full text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-3 py-2 text-right font-medium">فیلد</th>
            <th className="px-3 py-2 text-right font-medium">قبل</th>
            <th className="px-3 py-2 text-right font-medium">بعد</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {keys.map((key) => {
            const beforeValue = beforeObject[key]
            const afterValue = afterObject[key]
            const changed =
              JSON.stringify(beforeValue ?? null) !==
              JSON.stringify(afterValue ?? null)
            return (
              <tr key={key} className={changed ? 'bg-amber-50/60' : undefined}>
                <td className="px-3 py-2 font-medium text-slate-600">
                  {fieldLabel(key)}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {renderValue(beforeValue)}
                </td>
                <td
                  className={cn(
                    'px-3 py-2',
                    changed ? 'font-semibold text-slate-900' : 'text-slate-700',
                  )}
                >
                  {renderValue(afterValue)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function ActivityLogsPage() {
  const { user } = useAuth()
  const [logs, setLogs] = useState<ActivityLogListItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<FilterState>(EMPTY_FILTERS)
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [options, setOptions] = useState<ActivityLogFilterOptions | null>(null)
  const [detail, setDetail] = useState<ActivityLogDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  useEffect(() => {
    if (!user?.is_superuser) return
    const controller = new AbortController()
    fetchActivityLogFilters(controller.signal)
      .then(setOptions)
      .catch((cause) => {
        if (!isAbortError(cause)) setError(getErrorMessage(cause))
      })
    return () => controller.abort()
  }, [user?.is_superuser])

  useEffect(() => {
    if (!user?.is_superuser) return
    const controller = new AbortController()
    setLoading(true)
    const params: ActivityLogListParams = {
      actor: filters.actor || undefined,
      action: filters.action || undefined,
      module: filters.module || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      search: filters.search || undefined,
      page,
      page_size: PAGE_SIZE,
    }
    fetchActivityLogs(params, controller.signal)
      .then((response) => {
        setLogs(response.results)
        setTotalCount(response.count)
        setError(null)
      })
      .catch((cause) => {
        if (!isAbortError(cause)) setError(getErrorMessage(cause))
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [user?.is_superuser, filters, page])

  const activeFilterCount = useMemo(
    () =>
      Object.values(filters).filter((value) => value !== '').length,
    [filters],
  )

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE))

  if (!user?.is_superuser) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700 shadow-xs">
        دسترسی به گزارش فعالیت کاربران فقط برای Superuser مجاز است.
      </p>
    )
  }

  const applyFilters = (event: React.FormEvent) => {
    event.preventDefault()
    setPage(1)
    setFilters(draft)
  }

  const resetFilters = () => {
    setDraft(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
    setPage(1)
  }

  const openDetail = async (id: number) => {
    setDetailError(null)
    setDetailLoading(true)
    try {
      const data = await fetchActivityLog(id)
      setDetail(data)
    } catch (cause) {
      setDetailError(getErrorMessage(cause))
    } finally {
      setDetailLoading(false)
    }
  }

  const closeDetail = () => {
    setDetail(null)
    setDetailError(null)
  }

  return (
    <div className="space-y-5" dir="rtl">
      <PageHeader
        title="گزارش فعالیت کاربران"
        description="مرکز نظارت Superuser بر تمام عملیات مهم کاربران: چه کسی، چه زمانی، روی کدام رکورد و با چه نتیجه‌ای."
      />

      {error && (
        <p
          className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 shadow-xs"
          role="alert"
        >
          {error}
        </p>
      )}

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <form className="space-y-4 p-5" onSubmit={applyFilters}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <DualDateInput
              id="activity-from"
              label="از تاریخ"
              value={draft.date_from}
              onChange={(value) =>
                setDraft((previous) => ({ ...previous, date_from: value }))
              }
              allowGregorian={false}
            />
            <DualDateInput
              id="activity-to"
              label="تا تاریخ"
              value={draft.date_to}
              onChange={(value) =>
                setDraft((previous) => ({ ...previous, date_to: value }))
              }
              allowGregorian={false}
            />
            <Field label="انجام‌دهنده">
              <select
                className={inputClass}
                value={draft.actor}
                onChange={(event) =>
                  setDraft((previous) => ({ ...previous, actor: event.target.value }))
                }
              >
                <option value="">همه کاربران</option>
                {options?.actors.map((actor) => (
                  <option key={actor} value={actor}>
                    {actor}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="نوع عملیات">
              <select
                className={inputClass}
                value={draft.action}
                onChange={(event) =>
                  setDraft((previous) => ({ ...previous, action: event.target.value }))
                }
              >
                <option value="">همه عملیات‌ها</option>
                {options?.actions.map((action) => (
                  <option key={action} value={action}>
                    {actionLabel(action)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="بخش سیستم">
              <select
                className={inputClass}
                value={draft.module}
                onChange={(event) =>
                  setDraft((previous) => ({ ...previous, module: event.target.value }))
                }
              >
                <option value="">همه بخش‌ها</option>
                {(options?.modules ?? []).map((module) => (
                  <option key={module.value} value={module.value}>
                    {module.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="جستجو">
              <div className="relative">
                <SearchIcon className="absolute left-3 top-3 size-4 text-slate-400" />
                <input
                  type="text"
                  className={cn(inputClass, 'pl-9')}
                  placeholder="نام کاربری، شناسه یا شرح رکورد…"
                  value={draft.search}
                  onChange={(event) =>
                    setDraft((previous) => ({ ...previous, search: event.target.value }))
                  }
                />
              </div>
            </Field>
            <div className="flex items-end gap-2 sm:col-span-2">
              <Button type="submit" icon={<SearchIcon className="size-4" />}>
                اعمال فیلتر
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={resetFilters}
                disabled={activeFilterCount === 0}
              >
                حذف فیلترها
              </Button>
            </div>
          </div>
        </form>
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">سوابق فعالیت</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {toPersianDigits(totalCount)} رویداد ثبت‌شده
            </p>
          </div>
        </div>

        {loading ? (
          <p className="p-5 text-sm text-slate-500">در حال بارگذاری…</p>
        ) : logs.length === 0 ? (
          <EmptyState
            icon={<HistoryIcon className="size-6" />}
            title="فعالیتی برای نمایش وجود ندارد"
            description="با تغییر فیلترها یا بازهٔ تاریخ، دوباره جستجو کنید."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px] text-sm">
              <thead className="border-b border-slate-200 bg-slate-50/70 text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-right font-medium">تاریخ و ساعت</th>
                  <th className="px-5 py-3 text-right font-medium">انجام‌دهنده</th>
                  <th className="px-5 py-3 text-right font-medium">عملیات</th>
                  <th className="px-5 py-3 text-right font-medium">بخش</th>
                  <th className="px-5 py-3 text-right font-medium">رکورد</th>
                  <th className="px-5 py-3 text-right font-medium">نتیجه</th>
                  <th className="px-5 py-3 text-right font-medium">جزئیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((item) => (
                  <tr key={item.id} className="transition hover:bg-slate-50/70">
                    <td className="whitespace-nowrap px-5 py-3 text-slate-700">
                      {formatKabulDateTime(item.timestamp)}
                    </td>
                    <td className="px-5 py-3 font-mono text-slate-800" dir="ltr">
                      {item.actor_username || '—'}
                    </td>
                    <td className="px-5 py-3">
                      <p className="font-medium text-slate-800">
                        {actionLabel(item.action)}
                      </p>
                      <p className="font-mono text-[11px] text-slate-400" dir="ltr">
                        {item.action}
                      </p>
                    </td>
                    <td className="px-5 py-3 text-slate-700">
                      {moduleLabel(item.module)}
                    </td>
                    <td className="px-5 py-3">
                      {item.target_label ? (
                        <p className="text-slate-800">{item.target_label}</p>
                      ) : (
                        <p className="text-slate-400">—</p>
                      )}
                      {item.target_id && (
                        <p className="text-[11px] text-slate-400" dir="ltr">
                          {item.target_type ? `${item.target_type} · ` : ''}
                          #{toPersianDigits(item.target_id)}
                        </p>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <StatusPill status={item.status} />
                    </td>
                    <td className="px-5 py-3">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => openDetail(item.id)}
                      >
                        مشاهده
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={page}
          totalPages={totalPages}
          onChange={setPage}
        />
      </section>

      {(detail || detailLoading || detailError) && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/60 p-3 sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="activity-detail-title"
        >
          <section className="my-auto w-full max-w-3xl rounded-2xl bg-white shadow-2xl ring-1 ring-slate-900/10">
            <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 sm:px-6">
              <div>
                <h2
                  id="activity-detail-title"
                  className="text-base font-semibold text-slate-900"
                >
                  جزئیات فعالیت
                </h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  اطلاعات کامل رویداد ثبت‌شده در سابقهٔ سیستم.
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                icon={<XIcon className="size-4" />}
                aria-label="بستن پنجره"
                onClick={closeDetail}
              />
            </header>

            <div className="max-h-[70vh] overflow-y-auto p-5 sm:p-6">
              {detailLoading ? (
                <p className="text-sm text-slate-500">در حال بارگذاری…</p>
              ) : detailError ? (
                <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">
                  {detailError}
                </p>
              ) : detail ? (
                <div className="space-y-5">
                  <div className="grid gap-3 rounded-xl bg-slate-50 p-4 text-sm sm:grid-cols-2">
                    <p>
                      <span className="text-slate-500">انجام‌دهنده: </span>
                      <span className="font-mono font-medium text-slate-800" dir="ltr">
                        {detail.actor_username || '—'}
                      </span>
                    </p>
                    <p>
                      <span className="text-slate-500">تاریخ و ساعت: </span>
                      <span className="font-medium text-slate-800">
                        {formatKabulDateTime(detail.timestamp)}
                      </span>
                    </p>
                    <p>
                      <span className="text-slate-500">نوع عملیات: </span>
                      <span className="font-medium text-slate-800">
                        {actionLabel(detail.action)}
                      </span>
                    </p>
                    <p>
                      <span className="text-slate-500">بخش: </span>
                      <span className="font-medium text-slate-800">
                        {moduleLabel(detail.module)}
                      </span>
                    </p>
                    <p>
                      <span className="text-slate-500">رکورد هدف: </span>
                      <span className="font-medium text-slate-800">
                        {detail.target_label || '—'}
                        {detail.target_id &&
                          ` (#${toPersianDigits(detail.target_id)})`}
                      </span>
                    </p>
                    <p className="flex items-center gap-2">
                      <span className="text-slate-500">نتیجه: </span>
                      <StatusPill status={detail.status} />
                    </p>
                    <p className="sm:col-span-2">
                      <span className="text-slate-500">آدرس IP: </span>
                      <span className="font-mono font-medium text-slate-800" dir="ltr">
                        {detail.ip_address || 'ثبت نشده'}
                      </span>
                    </p>
                    {detail.description && (
                      <p className="sm:col-span-2">
                        <span className="text-slate-500">توضیح: </span>
                        <span className="text-slate-800">{detail.description}</span>
                      </p>
                    )}
                  </div>

                  {(detail.before_data || detail.after_data) && (
                    <div className="space-y-2">
                      <h3 className="text-sm font-semibold text-slate-800">
                        تغییرات رکورد
                      </h3>
                      <PayloadComparison
                        before={detail.before_data}
                        after={detail.after_data}
                      />
                    </div>
                  )}

                  {detail.metadata && Object.keys(detail.metadata).length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-sm font-semibold text-slate-800">
                        اطلاعات تکمیلی
                      </h3>
                      <div className="rounded-xl border border-slate-200 p-3">
                        <KeyValueList data={detail.metadata} />
                      </div>
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            <footer className="flex justify-end border-t border-slate-100 px-5 py-4 sm:px-6">
              <Button type="button" variant="secondary" onClick={closeDetail}>
                بستن
              </Button>
            </footer>
          </section>
        </div>
      )}
    </div>
  )
}
