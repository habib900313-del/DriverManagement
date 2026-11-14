import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowRightIcon, CalendarIcon, RefreshIcon } from '../components/icons'
import { Button } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import { correctPayment } from '../lib/api'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { CorrectPaymentInput } from '../types/financial'

export function PaymentCorrectPage() {
  const { id } = useParams()
  const paymentId = Number(id)
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<CorrectPaymentInput>({
    reason: '',
    new_amount: '',
    new_driver_id: undefined,
    new_payment_date: '',
    target_period_start: '',
    target_period_end: '',
  })
  const { notify } = useToast()

  useEffect(() => {
    setLoading(false)
  }, [])

  const handleChange = (key: keyof CorrectPaymentInput, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const payload: CorrectPaymentInput = {
        reason: form.reason,
        new_amount: form.new_amount || undefined,
        new_driver_id: form.new_driver_id,
        new_payment_date: form.new_payment_date || undefined,
        target_period_start: form.target_period_start || undefined,
        target_period_end: form.target_period_end || undefined,
      }
      await correctPayment(paymentId, payload)
      notify('success', 'پرداخت با موفقیت اصلاح شد.')
      navigate(`/financial`)
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

  if (!Number.isInteger(paymentId) || paymentId <= 0) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <p className="text-sm text-rose-700">شناسه پرداخت معتبر نیست.</p>
        <Link
          to="/financial"
          className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-600 transition hover:bg-white/60"
        >
          <ArrowRightIcon className="size-4" />
          بازگشت به داشبورد
        </Link>
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

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <PageHeader
          title="اصلاح پرداخت"
          description="اصلاح مبلغ یا تاریخ یا دوره هدف یک پرداخت ثبت‌شده. پرداخت اصلی حفظ شده و یک رکورد جدید ایجاد می‌شود."
        />

        <form onSubmit={handleSubmit} className="p-5 space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Field label="دلیل اصلاح (زامی)" required>
              <input
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.reason}
                onChange={(e) => handleChange('reason', e.target.value)}
                placeholder="دلیل اصلاح را بنویسید"
              />
            </Field>

            <Field label="مبلغ جدید (اختیاری - افغانی)">
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 font-mono dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.new_amount || ''}
                onChange={(e) => handleChange('new_amount', e.target.value)}
                placeholder="مبلغ جدید را وارد کنید"
              />
            </Field>

            <Field label="تاریخ پرداخت جدید (اختیاری - شمسی)">
              <input
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.new_payment_date || ''}
                onChange={(e) => handleChange('new_payment_date', e.target.value)}
                placeholder="۱۴۰۵/۰۸/۲۰"
              />
            </Field>

            <Field label="دوره هدف جدید - شروع (اختیاری - شمسی)">
              <input
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.target_period_start || ''}
                onChange={(e) => handleChange('target_period_start', e.target.value)}
                placeholder="۱۴۰۵/۰۸/۲۰"
              />
            </Field>

            <Field label="دوره هدف جدید - پایان (اختیاری - شمسی)">
              <input
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.target_period_end || ''}
                onChange={(e) => handleChange('target_period_end', e.target.value)}
                placeholder="۱۴۰۵/۱۱/۱۹"
              />
            </Field>
          </div>

          <div className="alert alert-info bg-blue-50 border-blue-200 p-4 rounded-lg">
            <h3 className="text-sm font-semibold text-blue-800">نکته مهم</h3>
            <p className="mt-1 text-sm text-blue-700">
              پرداخت اصلی حذف نمی‌شود و تنها وضعیت آن به "اصلاح‌شده" تغییر می‌کند.
              یک پرداخت جدید با مبلغ اصلاح شده ایجاد می‌شود و فقط مبلغ جدید در گزارش‌های نقدی شمارش می‌شود.
            </p>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button type="submit" loading={submitting} icon={<CalendarIcon className="size-4" />}>
              ثبت اصلاح
            </Button>
            <Button variant="secondary" size="sm" type="button" onClick={() => setForm({
              reason: '',
              new_amount: '',
              new_driver_id: undefined,
              new_payment_date: '',
              target_period_start: '',
              target_period_end: '',
            })}>
              پاک کردن فرم
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}