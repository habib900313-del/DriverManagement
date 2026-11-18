import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams, useParams } from 'react-router-dom'
import { ArrowRightIcon, CreditCardIcon, RefreshIcon } from '../components/icons'
import { DualDateInput } from '../components/DualDateInput'
import { Button } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import {
  fetchDriver,
  fetchDrivers,
  receivePayment,
  fetchDriverPeriodCoverage,
} from '../lib/api'
import {
  formatJalaliShort,
  isValidIsoDate,
  todayIsoKabul,
  toPersianDigits,
} from '../lib/dates'
import { getErrorMessage, isAbortError, normalizeDigits } from '../lib/errors'
import type { Driver, DriverListParams } from '../types/driver'
import type {
  DriverPeriodCoverage,
  PeriodCoverageRow,
  ReceivePaymentInput,
} from '../types/financial'

function formatAmount(value: number): string {
  return toPersianDigits(
    new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value),
  )
}

type PeriodFilter = 'all' | 'with-debt' | 'settled'

const PERIOD_FILTER_LABELS: Record<PeriodFilter, string> = {
  all: 'همه دوره‌ها',
  'with-debt': 'دارای بدهی',
  settled: 'تسویه‌شده',
}

function periodStatusLabel(status: PeriodCoverageRow['status']): string {
  switch (status) {
    case 'paid':
      return 'تسویه‌شده'
    case 'partial':
      return 'پرداخت جزئی'
    case 'unpaid':
      return 'پرداخت‌نشده'
    default:
      return status
  }
}

function periodStatusBadge(status: PeriodCoverageRow['status']): string {
  switch (status) {
    case 'paid':
      return 'bg-emerald-100 text-emerald-700 border-emerald-200'
    case 'partial':
      return 'bg-amber-100 text-amber-700 border-amber-200'
    case 'unpaid':
      return 'bg-rose-100 text-rose-700 border-rose-200'
    default:
      return 'bg-slate-100 text-slate-600 border-slate-200'
  }
}

export function PaymentRegisterPage() {
  const [searchParams] = useSearchParams()
  const { id } = useParams()
  const prefillDriverId = searchParams.get('driver_id') || id

  const [driver, setDriver] = useState<Driver | null>(null)
  const [drivers, setDrivers] = useState<Driver[]>([])
  const [coverage, setCoverage] = useState<DriverPeriodCoverage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<{
    amount?: string
    paymentDate?: string
    targetPeriod?: string
  }>({})
  const [periodFilter, setPeriodFilter] = useState<PeriodFilter>('all')
  const [selectedPeriodKey, setSelectedPeriodKey] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const [form, setForm] = useState<ReceivePaymentInput>({
    driver_id: prefillDriverId ? Number(prefillDriverId) : 0,
    amount: '',
    payment_date: todayIsoKabul(),
    target_period_start: '',
    target_period_end: '',
  })
  const { notify } = useToast()

  const loadDriverData = useCallback((driverId: number) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setError(null)
    Promise.all([
      fetchDriver(driverId, controller.signal),
      fetchDriverPeriodCoverage(driverId, undefined, controller.signal),
    ])
      .then(([drv, cov]) => {
        if (!controller.signal.aborted) {
          setDriver(drv)
          setCoverage(cov)
          setForm((prev) => ({ ...prev, driver_id: drv.id }))
          // Reset selection when driver data reloads
          setSelectedPeriodKey(null)
          setForm((prev) => ({
            ...prev,
            target_period_start: '',
            target_period_end: '',
          }))
        }
      })
      .catch((cause) => {
        if (!controller.signal.aborted && !isAbortError(cause)) {
          setError(getErrorMessage(cause))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => {
      controller.abort()
    }
  }, [])

  useEffect(() => {
    // Load all drivers for the dropdown
    const params: DriverListParams = {
      status: 'active',
      page_size: 100,
    }
    fetchDrivers(params)
      .then((response) => {
        setDrivers(response.results)
      })
      .catch((cause) => {
        console.error('Failed to load drivers:', cause)
      })

    // Load prefilled driver data if provided
    if (prefillDriverId) {
      loadDriverData(Number(prefillDriverId))
    } else {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const periodsList = useMemo(
    () => coverage?.periods || [],
    [coverage],
  )

  const filteredPeriods = useMemo(() => {
    return periodsList.filter((p) => {
      if (periodFilter === 'settled') return p.status === 'paid'
      if (periodFilter === 'with-debt') return p.status === 'partial' || p.status === 'unpaid'
      return true
    })
  }, [periodsList, periodFilter])

  const selectedPeriod = useMemo(
    () =>
      selectedPeriodKey
        ? periodsList.find((p) => `${p.start},${p.end}` === selectedPeriodKey) || null
        : null,
    [periodsList, selectedPeriodKey],
  )

  const amount = normalizeDigits(form.amount).trim()
  const amountNum = /^\d+$/.test(amount) ? Number(amount) : 0

  // Compute Own-First allocation preview starting from selected period
  const allocationPreview = useMemo(() => {
    if (!selectedPeriod || amountNum <= 0) return []

    const preview: Array<{ period: PeriodCoverageRow; allocated: number }> = []
    let remainder = amountNum
    const startIndex = periodsList.findIndex(
      (p) => p.start === selectedPeriod.start && p.end === selectedPeriod.end,
    )
    if (startIndex < 0) return []

    for (let i = startIndex; i < periodsList.length && remainder > 0; i += 1) {
      const p = periodsList[i]
      // Skip already fully paid periods — they have no remaining debt
      const remaining = Number(p.remaining)
      if (remaining <= 0) continue
      const allocated = Math.min(remaining, remainder)
      if (allocated > 0) {
        preview.push({ period: p, allocated })
        remainder -= allocated
      }
    }
    return preview
  }, [selectedPeriod, amountNum, periodsList])

  const totalAllocated = useMemo(
    () =>
      allocationPreview.reduce((sum, item) => sum + item.allocated, 0),
    [allocationPreview],
  )

  const previewRemainder = amountNum - totalAllocated

  const handleSelectDriver = (id: number) => {
    if (!id) {
      setDriver(null)
      setCoverage(null)
      setSelectedPeriodKey(null)
      setForm((prev) => ({
        ...prev,
        driver_id: 0,
        amount: '',
        target_period_start: '',
        target_period_end: '',
      }))
      return
    }
    loadDriverData(id)
  }

  const handleSelectPeriod = (period: PeriodCoverageRow) => {
    // Prevent selecting fully paid periods
    if (period.status === 'paid') return
    setSelectedPeriodKey(`${period.start},${period.end}`)
    setForm((prev) => ({
      ...prev,
      target_period_start: period.start,
      target_period_end: period.end,
    }))
    setFieldErrors((current) => ({ ...current, targetPeriod: undefined }))
  }

  const handleChange = (key: keyof ReceivePaymentInput, value: string | number) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    const nextFieldErrors: typeof fieldErrors = {}

    if (!/^\d+$/.test(amount) || amountNum <= 0) {
      nextFieldErrors.amount = 'مبلغ باید یک عدد صحیح بزرگ‌تر از صفر باشد.'
    }
    if (!isValidIsoDate(form.payment_date)) {
      nextFieldErrors.paymentDate = 'تاریخ پرداخت را از تقویم انتخاب کنید.'
    } else if (form.payment_date > todayIsoKabul()) {
      nextFieldErrors.paymentDate = 'تاریخ پرداخت نمی‌تواند در آینده باشد.'
    }
    if (!driver) {
      setError('راننده معتبر انتخاب نشده است.')
    }
    if (!selectedPeriod) {
      nextFieldErrors.targetPeriod = 'یک دوره مالی قابل پرداخت انتخاب کنید.'
    }

    // Frontend validation: amount must not exceed total remaining debt of selectable periods
    const selectableRemaining = periodsList
      .filter((p) => p.status !== 'paid')
      .reduce((sum, p) => sum + Number(p.remaining), 0)
    if (
      selectedPeriod &&
      /^\d+$/.test(amount) &&
      amountNum > selectableRemaining &&
      selectableRemaining > 0
    ) {
      nextFieldErrors.amount =
        'مبلغ پرداختی بیشتر از کل بدهی معتبر دوره‌های قابل پرداخت است.'
    }

    setFieldErrors(nextFieldErrors)
    if (Object.keys(nextFieldErrors).length > 0 || !driver || !selectedPeriod) {
      notify('error', 'اطلاعات پرداخت را بررسی کنید.')
      return
    }

    setSubmitting(true)
    try {
      const payload: ReceivePaymentInput = {
        driver_id: driver.id,
        amount,
        payment_date: form.payment_date,
        target_period_start: form.target_period_start,
        target_period_end: form.target_period_end,
      }
      const result = await receivePayment(payload)
      notify('success', `پرداخت ${toPersianDigits(result.amount)} AFN با موفقیت ثبت شد.`)

      // Refresh driver data after successful payment to update period statuses
      if (driver.id) {
        loadDriverData(driver.id)
      }
      setForm((prev) => ({
        ...prev,
        amount: '',
        target_period_start: '',
        target_period_end: '',
      }))
      setSelectedPeriodKey(null)
    } catch (cause) {
      if (!isAbortError(cause)) {
        const msg = getErrorMessage(cause)
        setError(msg)
        notify('error', msg)
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm">
        <div className="size-7 animate-spin rounded-full border-4 border-slate-200 border-t-slate-900" />
        <p className="text-sm">در حال بارگذاری…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <p className="text-sm text-rose-700">{error}</p>
        <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
          <RefreshIcon className="size-4" />
          تلاش دوباره
        </Button>
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
        {driver && (
          <Link
            to={`/financial/drivers/${driver.id}`}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition hover:text-slate-900"
          >
            مشاهده پروفایل مالی راننده
          </Link>
        )}
      </div>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <PageHeader
          title="ثبت پرداخت جدید"
          description="مبلغ پرداخت از دورهٔ انتخاب‌شده آغاز می‌شود و مانده به‌ترتیب به دوره‌های بعدی می‌رسد."
        />

        <form onSubmit={handleSubmit} className="p-5 space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Field
              label="راننده"
              required
              error={!driver ? 'راننده معتبر انتخاب نشده است.' : undefined}
            >
              {prefillDriverId && driver ? (
                <input
                  readOnly
                  value={`${driver.full_name} (${driver.driver_code})`}
                  className="block w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 shadow-xs"
                />
              ) : (
                <select
                  className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                  value={form.driver_id || ''}
                  onChange={(event) => {
                    handleSelectDriver(Number(event.target.value))
                  }}
                >
                  <option value="">انتخاب راننده</option>
                  {drivers.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.full_name} ({d.driver_code})
                    </option>
                  ))}
                </select>
              )}
            </Field>

            <Field label="مبلغ (افغانی)" required>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9۰-۹٠-٩]*"
                className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 font-mono dir-ltr shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                value={form.amount}
                onChange={(event) => {
                  handleChange('amount', event.target.value)
                  setFieldErrors((current) => ({ ...current, amount: undefined }))
                }}
                placeholder="مثلاً 600"
                aria-invalid={Boolean(fieldErrors.amount)}
              />
              {fieldErrors.amount && (
                <p className="mt-1 text-xs text-rose-600">{fieldErrors.amount}</p>
              )}
            </Field>

            <DualDateInput
              id="payment_date"
              label="تاریخ پرداخت"
              value={form.payment_date}
              onChange={(value) => {
                handleChange('payment_date', value)
                setFieldErrors((current) => ({ ...current, paymentDate: undefined }))
              }}
              required
              error={fieldErrors.paymentDate}
              hint="تاریخ را از تقویم شمسی انتخاب کنید."
            />
          </div>

          {/* Period filter */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-slate-600">فیلتر دوره‌ها:</span>
            {(Object.keys(PERIOD_FILTER_LABELS) as PeriodFilter[]).map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setPeriodFilter(filter)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                  periodFilter === filter
                    ? 'border-brand-500 bg-brand-50 text-brand-700'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {PERIOD_FILTER_LABELS[filter]}
              </button>
            ))}
          </div>

          {/* Smart period list */}
          <div
            className="grid gap-2"
            style={{
              gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            }}
          >
            {filteredPeriods.length === 0 ? (
              <div className="col-span-full p-4 rounded-xl border border-slate-200 bg-slate-50 text-center text-sm text-slate-500">
                دوره‌ای با این فیلتر یافت نشد.
              </div>
            ) : (
              filteredPeriods.map((period) => {
                const isSelected = selectedPeriodKey === `${period.start},${period.end}`
                const isPaid = period.status === 'paid'
                const isOverdue = period.is_overdue && Number(period.remaining) > 0
                const remainingNum = Number(period.remaining)
                const paidNum = Number(period.paid)
                const totalNum = Number(period.total)

                return (
                  <button
                    key={period.start}
                    type="button"
                    onClick={() => handleSelectPeriod(period)}
                    disabled={isPaid}
                    className={`
                      rounded-xl border p-3 transition-all duration-200
                      ${isSelected
                        ? 'border-brand-500 bg-brand-50 shadow-sm ring-1 ring-brand-500'
                        : isPaid
                        ? 'border-slate-200 bg-slate-50 text-slate-400 opacity-60'
                        : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
                      }
                    `}
                    title={
                      period.is_future
                        ? 'دوره آینده — هنوز شروع نشده است'
                        : isOverdue
                        ? 'دوره معوق — سررسید گذشته است'
                        : ''
                    }
                  >
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <span
                        className={`text-xs font-medium leading-none ${
                          isSelected ? 'text-brand-700' : 'text-slate-700'
                        }`}
                      >
                        #{periodsList.findIndex(
                          (p) => p.start === period.start && p.end === period.end,
                        ) +
                        1}
                      </span>
                      {isSelected && (
                        <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold border border-brand-500 text-brand-700 bg-brand-50">
                          انتخاب‌شده
                        </span>
                      )}
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between items-baseline">
                        <span className="text-xs text-slate-500">شروع — پایان</span>
                        <span className="text-xs font-mono text-slate-700 dir-ltr">
                          {formatJalaliShort(period.start)} — {formatJalaliShort(
                            period.end,
                          )}
                        </span>
                      </div>

                      <div className="flex justify-between items-baseline">
                        <span className="text-xs text-slate-500">مبلغ کل دوره</span>
                        <span className="text-xs font-mono text-slate-700 dir-ltr">
                          {toPersianDigits(totalNum.toFixed(0))} AFN
                        </span>
                      </div>

                      <div className="flex justify-between items-baseline">
                        <span className="text-xs text-slate-500">پرداخت‌شده</span>
                        <span className="text-xs font-mono text-emerald-600 dir-ltr">
                          {toPersianDigits(paidNum.toFixed(0))} AFN
                        </span>
                      </div>

                      <div className="flex justify-between items-baseline">
                        <span className="text-xs text-slate-500">باقی‌مانده</span>
                        <span
                          className={`text-xs font-bold font-mono dir-ltr ${
                            remainingNum === 0
                              ? 'text-emerald-600'
                              : isOverdue
                              ? 'text-rose-600'
                              : 'text-slate-700'
                          }`}
                        >
                          {toPersianDigits(remainingNum.toFixed(0))} AFN
                        </span>
                      </div>

                      <span
                        className={`inline-flex items-center justify-center rounded-full px-2 py-0.5 text-[10px] font-bold border ${
                          periodStatusBadge(period.status)
                        }`}
                      >
                        {periodStatusLabel(period.status)}
                        {period.is_overdue && remainingNum > 0 && ' • معوق'}
                      </span>

                      {period.is_future && (
                        <span className="text-[10px] text-slate-400 italic mt-0.5">
                          هنوز شروع نشده است
                        </span>
                      )}
                    </div>
                  </button>
                )
              })
            )}
          </div>

          <fieldset className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <legend className="px-1 text-sm font-semibold text-slate-800">روش تخصیص پرداخت</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label
                className="flex cursor-pointer items-start gap-3 rounded-xl border border-brand-500 bg-brand-50 p-3 shadow-xs transition"
              >
                <input
                  type="radio"
                  name="allocation-method"
                  value="period"
                  checked
                  readOnly
                  className="mt-0.5"
                />
                <span>
                  <span className="block text-sm font-medium text-slate-800">
                    تخصیص خودکار به دوره‌ها
                  </span>
                  <span className="mt-1 block text-xs text-slate-500">
                    مبلغ از دورهٔ انتخاب‌شده آغاز می‌شود و مابقی به‌ترتیب میان دوره‌های بعدی تقسیم می‌شود.
                  </span>
                </span>
              </label>
            </div>
          </fieldset>

          {/* Allocation preview */}
          {allocationPreview.length > 0 && (
            <section
              aria-live="polite"
              className="rounded-xl border border-brand-100 bg-brand-50/60 p-4"
            >
              <h3 className="text-sm font-semibold text-slate-800">
                پیش‌نمایش تخصیص خودکار
              </h3>
              <p className="mt-1 text-xs text-slate-600">
                مبلغ از دورهٔ انتخاب‌شده آغاز می‌شود و ماندهٔ آن به‌ترتیب به دوره‌های بعدی می‌رسد.
              </p>
              <ul className="mt-3 divide-y divide-brand-100">
                {allocationPreview.map(({ period, allocated }) => (
                  <li
                    key={period.start}
                    className="flex items-center justify-between gap-3 py-2 text-sm"
                  >
                    <span className="text-slate-700">
                      {formatJalaliShort(period.start)} تا {formatJalaliShort(
                        period.end,
                      )}
                    </span>
                    <span className="font-mono font-semibold text-slate-800" dir="ltr">
                      {formatAmount(allocated)} AFN
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-brand-100 pt-3 text-sm">
                <span className="font-medium text-slate-700">مجموع تخصیص‌شده</span>
                <span className="font-mono font-semibold text-slate-900" dir="ltr">
                  {formatAmount(totalAllocated)} AFN
                </span>
              </div>
              {previewRemainder > 0 && (
                <p className="mt-2 text-xs text-amber-700">
                  بقیه مانده در دوره‌های بعدی هنگام ثبت به‌صورت خودکار ادامه می‌یابد.
                </p>
              )}
            </section>
          )}

          <div className="flex items-center gap-3 pt-2">
            <Button
              type="submit"
              loading={submitting}
              disabled={!driver || !selectedPeriod || amountNum <= 0}
              icon={<CreditCardIcon className="size-4" />}
            >
              ثبت پرداخت
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setForm((prev) => ({
                  ...prev,
                  amount: '',
                }))
              }}
            >
              پاک کردن مبلغ
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}
