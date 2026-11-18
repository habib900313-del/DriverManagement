import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowRightIcon, CalendarIcon, RefreshIcon } from '../components/icons'
import { Button } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import { correctAllocation } from '../lib/api'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { CorrectAllocationInput } from '../types/financial'

export function AllocationCorrectPage() {
  const { id } = useParams()
  const allocationId = Number(id)
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<CorrectAllocationInput>({
    reason: '',
    new_target_period_start: '',
    new_target_period_end: '',
  })
  const { notify } = useToast()

  useEffect(() => {
    setLoading(false)
  }, [])

  const handleChange = (key: keyof CorrectAllocationInput, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const payload: CorrectAllocationInput = {
        reason: form.reason,
        new_target_period_start: form.new_target_period_start,
        new_target_period_end: form.new_target_period_end,
      }
      await correctAllocation(allocationId, payload)
      notify('success', 'تخصیص با موفقیت اصلاح شد.')
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
        <p className="text-sm text-rose-700">شناسه تخصیص معتبر نیست.</p>
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
          title="اصلاح تخصیص پرداخت"
          description="تغییر دوره هدف یک تخصیص پرداخت. پرداخت اصلی حفظ شده و فقط تخصیص تغییر می‌کند."
        />

        <form onSubmit={handleSubmit} className="p-5 space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Field label="دلیل اصلاح (زامی)" required>
              <input
                className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                defaultValue={form.reason}
                onChange={(e) => handleChange('reason', e.target.value)}
                placeholder="دلیل اصلاح تخصصی را بنویسید"
              />
            </Field>

            <Field label="تاریخ شروع دوره جدید (شمسی)" required>
              <input
                className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                defaultValue={form.new_target_period_start}
                onChange={(e) => handleChange('new_target_period_start', e.target.value)}
                placeholder="۱۴۰۵/۰۸/۲۰"
              />
            </Field>

            <Field label="تاریخ پایان دوره جدید (شمسی)" required>
              <input
                className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                defaultValue={form.new_target_period_end}
                onChange={(e) => handleChange('new_target_period_end', e.target.value)}
                placeholder="۱۴۰۵/۱۱/۱۹"
              />
            </Field>
          </div>

          <div className="rounded-xl border border-brand-200 bg-brand-50 p-4">
            <h3 className="text-sm font-semibold text-brand-800">نکته مهم</h3>
            <p className="mt-1 text-sm text-brand-700">
              فقط تخصیص‌های نوع "فیس دوره" قابل اصلاح هستند. تخصیص‌های اعتباری باabhängی به مصرف‌ها
              باید از طریق صفحه "اصلاح تخصیص اعتباری" اصلاح شوند.
            </p>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button type="submit" loading={submitting} icon={<CalendarIcon className="size-4" />}>
              ثبت اصلاح تخصیص
            </Button>
            <Button variant="secondary" size="sm" type="button" onClick={() => setForm({
              reason: '',
              new_target_period_start: '',
              new_target_period_end: '',
            })}>
              پاک کردن فرم
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}