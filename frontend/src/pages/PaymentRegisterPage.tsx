import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowRightIcon, CreditCardIcon, RefreshIcon } from '../components/icons'
import { Button } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import {
  fetchDriver,
  receivePayment,
  fetchDriverPeriods,
} from '../lib/api'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { ReceivePaymentInput } from '../types/financial'

export function PaymentRegisterPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { id } = useParams()
  const prefillDriverId = searchParams.get('driver_id') || id
  const [driver, setDriver] = useState<any>(null)
  const [periods, setPeriods] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [allocationMethod, setAllocationMethod] = useState<'period' | 'credit'>('period')
  const [form, setForm] = useState<ReceivePaymentInput>({
    driver_id: prefillDriverId ? Number(prefillDriverId) : 0,
    amount: '',
    payment_date: new Date().toISOString().split('T')[0],
    target_period_start: '',
    target_period_end: '',
    periods_count: 1,
    receipt_number: '',
    idempotency_key: '',
  })
  const { notify } = useToast()

  useEffect(() => {
    if (!prefillDriverId) {
      setLoading(false)
      return
    }
    let active = true
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    Promise.all([
      fetchDriver(Number(prefillDriverId), controller.signal),
      fetchDriverPeriods(Number(prefillDriverId), controller.signal, 4),
    ])
      .then(([drv, per]) => {
        if (active) {
          setDriver(drv)
          setPeriods(per)
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
  }, [prefillDriverId])

  const handleChange = (key: keyof ReceivePaymentInput, value: string | number) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      if (
        allocationMethod === 'period' &&
        (!form.target_period_start || !form.target_period_end)
      ) {
        const message = 'برای تخصیص به دوره‌های مشخص، یک دوره مالی را انتخاب کنید.'
        setError(message)
        notify('error', message)
        return
      }
      const payload: ReceivePaymentInput = {
        driver_id: form.driver_id,
        amount: form.amount,
        payment_date: form.payment_date,
        target_period_start:
          allocationMethod === 'period' ? form.target_period_start || undefined : undefined,
        target_period_end:
          allocationMethod === 'period' ? form.target_period_end || undefined : undefined,
        periods_count: allocationMethod === 'period' ? Number(form.periods_count) || 1 : 1,
        receipt_number: form.receipt_number,
        idempotency_key: form.idempotency_key || undefined,
      }
      const result = await receivePayment(payload)
      notify('success', `پرداخت ${toPersianDigits(result.amount)} AFN با موفقیت ثبت شد.`)
      navigate(`/drivers/${result.driver}`)
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

  const periodOptions = (periods?.periods || []).map((p: any) => ({
    label: `${formatJalaliShort(p.start)} تا ${formatJalaliShort(p.end)}${
      p.fee ? ` — ${toPersianDigits(p.fee)} AFN` : ''
    }`,
    value: `${p.start},${p.end}`,
  }))

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
            مشاهده پروفایل مالی ranنده
          </Link>
        )}
      </div>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <PageHeader
          title="ثبت پرداخت جدید"
          description="ثبت حق‌الزحمه و تعیین روش تخصیص آن."
        />

        <form onSubmit={handleSubmit} className="p-5 space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Field
              label="راننده"
              required
              error={!driver ? 'راننده معتبر انتخاب نشده است.' : undefined}
            >
              <select
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.driver_id || ''}
                onChange={(e) => handleChange('driver_id', e.target.value)}
              >
                <option value="">انتخاب Ranنده</option>
                {driver && (
                  <option value={driver.id} selected>
                    {driver.full_name} ({driver.driver_code})
                  </option>
                )}
              </select>
            </Field>

            <Field label="مبلغ (افغانی)" required>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 font-mono dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.amount}
                onChange={(e) => handleChange('amount', e.target.value)}
                placeholder="مثلاً 600"
              />
            </Field>

            <Field label="تاریخ پرداخت (شمسی)" required>
              <input
                type="text"
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.payment_date}
                onChange={(e) => handleChange('payment_date', e.target.value)}
                placeholder="۱۴۰۵/۰۸/۲۰"
              />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Field label="شماره رسید (اختیاری)">
              <input
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.receipt_number}
                onChange={(e) => handleChange('receipt_number', e.target.value)}
                placeholder="شماره رسید"
              />
            </Field>

            <Field label="کلید تکرارپذیری (اختیاری)">
              <input
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.idempotency_key}
                onChange={(e) => handleChange('idempotency_key', e.target.value)}
                placeholder="شناسه یکتا درخواست"
              />
            </Field>

          </div>

          <fieldset className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <legend className="px-1 text-sm font-semibold text-slate-800">روش تخصیص پرداخت</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
                  allocationMethod === 'period'
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <input
                  type="radio"
                  name="allocation-method"
                  value="period"
                  checked={allocationMethod === 'period'}
                  onChange={() => setAllocationMethod('period')}
                  className="mt-0.5"
                />
                <span>
                  <span className="block text-sm font-medium text-slate-800">تخصیص به دوره‌های مشخص</span>
                  <span className="mt-1 block text-xs text-slate-500">
                    پرداخت را برای یک یا چند دورهٔ متوالی انتخاب کنید.
                  </span>
                </span>
              </label>
              <label
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
                  allocationMethod === 'credit'
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <input
                  type="radio"
                  name="allocation-method"
                  value="credit"
                  checked={allocationMethod === 'credit'}
                  onChange={() => setAllocationMethod('credit')}
                  className="mt-0.5"
                />
                <span>
                  <span className="block text-sm font-medium text-slate-800">ثبت به‌عنوان اعتبار</span>
                  <span className="mt-1 block text-xs text-slate-500">
                    پرداخت بدون اتصال مستقیم به یک دوره ثبت می‌شود.
                  </span>
                </span>
              </label>
            </div>
          </fieldset>

          {allocationMethod === 'period' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="دوره هدف" required>
                <select
                  className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  value={
                    form.target_period_start && form.target_period_end
                      ? `${form.target_period_start},${form.target_period_end}`
                      : ''
                  }
                  onChange={(e) => {
                    const val = e.target.value
                    if (!val) {
                      handleChange('target_period_start', '')
                      handleChange('target_period_end', '')
                      return
                    }
                    const [start, end] = val.split(',')
                    handleChange('target_period_start', start)
                    handleChange('target_period_end', end)
                  }}
                >
                  <option value="">انتخاب دوره مالی</option>
                  {periodOptions.map((opt: { label: string; value: string }) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="تعداد دوره‌های پوشش‌داده‌شده">
                <select
                  className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  value={String(form.periods_count ?? 1)}
                  onChange={(e) => handleChange('periods_count', Number(e.target.value))}
                >
                  {[1, 2, 3, 4].map((count) => (
                    <option key={count} value={count}>
                      {toPersianDigits(count.toString())} دوره
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <Button type="submit" loading={submitting} icon={<CreditCardIcon className="size-4" />}>
              ثبت پرداخت
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setForm((prev) => ({ ...prev, amount: '', receipt_number: '', idempotency_key: '' }))
              }}
            >
              پاک کردن فرم
            </Button>
          </div>
        </form>
      </section>

      {driver && (
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
            <h2 className="text-sm font-semibold text-slate-800">دوره‌های مالی</h2>
            <div className="overflow-x-auto p-3">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="bg-slate-50 text-xs text-slate-500">
                  <tr>
                    <th className="px-4 py-2 text-right font-medium">دوره</th>
                    <th className="px-4 py-2 text-right font-middle" dir="ltr">شروع</th>
                    <th className="px-4 py-2 text-right font-middle" dir="ltr">پایان</th>
                    <th className="px-4 py-2 text-right font-middle" dir="ltr">مبلغ دوره</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(periods?.periods || []).map((p: any, idx: number) => (
                    <tr key={idx} className="transition hover:bg-slate-50/70">
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
                        {p.fee != null ? `${toPersianDigits(p.fee)} AFN` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
