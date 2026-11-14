import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowRightIcon, CreditCardIcon, RefreshIcon } from '../components/icons'
import { Button } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import { correctCreditAllocation } from '../lib/api'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { CorrectCreditInput } from '../types/financial'

export function AllocationCorrectCreditPage() {
  const { id } = useParams()
  const allocationId = Number(id)
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<CorrectCreditInput>({
    reason: '',
    new_credit_amount: '',
    fee_allocations: [],
    consumptions: [],
  })
  const { notify } = useToast()

  useEffect(() => {
    setLoading(false)
  }, [])

  const handleChange = (key: keyof CorrectCreditInput, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const payload: CorrectCreditInput = {
        reason: form.reason,
        new_credit_amount: form.new_credit_amount,
        fee_allocations: form.fee_allocations,
        consumptions: form.consumptions,
      }
      await correctCreditAllocation(allocationId, payload)
      notify('success', 'تخصیص اعتباری با موفقیت اصلاح شد.')
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

  if (!Number.isInteger(allocationId) || allocationId <= 0) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <p className="text-sm text-rose-700">شناسه تخصیص اعتباری معتبر نیست.</p>
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
          title="اصلاح تخصیص اعتباری"
          description="تعدیل تخصیص اعتباری و بازگرداندن weighted consumptions وابسته. потребу تأیید مجدد مدیر برای مصارف جدید."
        />

        <form onSubmit={handleSubmit} className="p-5 space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Field label="دلیل اصلاح (زامی)" required>
              <input
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.reason}
                onChange={(e) => handleChange('reason', e.target.value)}
                placeholder="دلیل اصلاح تخصیص اعتباری"
              />
            </Field>

            <Field label="مبلغ اعتبار جدید (افغانی)">
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 font-mono dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                defaultValue={form.new_credit_amount}
                onChange={(e) => handleChange('new_credit_amount', e.target.value)}
                placeholder="مقدار اعتبار جدید"
              />
            </Field>
          </div>

          <div className="alert alert-warning bg-rose-50 border-rose-200 p-4 rounded-lg">
            <h3 className="text-sm font-semibold text-rose-800">روند اصلاح اعتباری</h3>
            <p className="mt-1 text-sm text-rose-700">
              ۱. تمام مصارف وابسته به تخصیص کنونی بازمی‌گردانند.<br />
              ۲. تخصیص کنونی بازگردانده می‌شود.<br />
              ۳. تخصیص‌های جدید (فیس و اعتبار) ایجاد می‌شوند.<br />
              ۴. مصارف جدید فقط با تأیید مدیر ثبت می‌شوند.
            </p>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button type="submit" loading={submitting} icon={<CreditCardIcon className="size-4" />}>
              ثبت اصلاح تخصیص اعتباری
            </Button>
            <Button variant="secondary" size="sm" type="button" onClick={() => setForm({
              reason: '',
              new_credit_amount: '',
              fee_allocations: [],
              consumptions: [],
            })}>
              پاک کردن فرم
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}