import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  CheckIcon,
  CreditCardIcon,
  InfoIcon,
  PencilIcon,
  RefreshIcon,
} from '../components/icons'
import { Button } from '../components/ui/Button'
import { Field, inputClass } from '../components/ui/Field'
import { useToast } from '../context/ToastContext'
import { correctPayment, fetchPayment } from '../lib/api'
import { cn } from '../lib/cn'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import { getPaymentCorrectionDisabledReason } from '../lib/payments'
import type { PaymentListItem } from '../types/financial'

interface CorrectionForm {
  reason: string
  amount: string
  paymentDate: string
}

export function PaymentCorrectPage() {
  const { id } = useParams()
  const [searchParams] = useSearchParams()
  const requestedReturnTo = searchParams.get('returnTo')
  const returnTo =
    requestedReturnTo && /^\/drivers\/\d+$/.test(requestedReturnTo)
      ? requestedReturnTo
      : null
  const paymentId = Number(id)
  const navigate = useNavigate()
  const { notify } = useToast()
  const [payment, setPayment] = useState<PaymentListItem | null>(null)
  const [form, setForm] = useState<CorrectionForm>({
    reason: '',
    amount: '',
    paymentDate: '',
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!Number.isInteger(paymentId) || paymentId <= 0) {
      return
    }

    const controller = new AbortController()
    fetchPayment(paymentId, controller.signal)
      .then((result) => {
        setPayment(result)
        setForm({
          reason: '',
          amount: result.amount,
          paymentDate: result.payment_date,
        })
      })
      .catch((cause) => {
        if (!isAbortError(cause)) setError(getErrorMessage(cause))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [paymentId, retry])

  const isLoading = loading || (!error && payment?.id !== paymentId)
  const retryLoad = () => {
    setError(null)
    setLoading(true)
    setRetry((value) => value + 1)
  }

  if (!Number.isInteger(paymentId) || paymentId <= 0) {
    return <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 shadow-xs">شناسه پرداخت معتبر نیست.</p>
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!payment) return

    const amountChanged = form.amount !== payment.amount
    const dateChanged = form.paymentDate !== payment.payment_date
    if (!form.reason.trim()) {
      const message = 'دلیل اصلاح الزامی است.'
      setError(message)
      notify('error', message)
      return
    }
    if (!amountChanged && !dateChanged) {
      const message = 'مبلغ یا تاریخ پرداخت را تغییر دهید.'
      setError(message)
      notify('error', message)
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const replacement = await correctPayment(payment.id, {
        reason: form.reason.trim(),
        new_amount: amountChanged ? form.amount : undefined,
        new_payment_date: dateChanged ? form.paymentDate : undefined,
      })
      notify('success', 'پرداخت اصلاح شد؛ سابقه اصلی و reversal حفظ شده‌اند.')
      navigate(returnTo ?? `/financial/payments/${replacement.id}`)
    } catch (cause) {
      if (!isAbortError(cause)) {
        const message = getErrorMessage(cause)
        setError(message)
        notify('error', message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        <span className="size-8 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" />
        <p className="text-sm text-slate-500">در حال بارگذاری پرداخت…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <span className="grid size-11 place-items-center rounded-full bg-rose-100 text-rose-600">
          <AlertTriangleIcon className="size-5" />
        </span>
        <p className="text-sm text-rose-700">{error}</p>
        <Button variant="secondary" size="sm" onClick={retryLoad}>
          <RefreshIcon className="size-4" />
          تلاش دوباره
        </Button>
      </div>
    )
  }

  if (!payment) return null
  const correctionBlockedReason = getPaymentCorrectionDisabledReason(payment)
  const amountChanged = form.amount !== payment.amount
  const dateChanged = form.paymentDate !== payment.payment_date

  return (
    <div className="space-y-5">
      <Link
        to={`/financial/payments/${payment.id}`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition-colors hover:text-brand-700"
      >
        <ArrowRightIcon className="size-4" />
        بازگشت به جزئیات پرداخت
      </Link>

      <section className="animate-fade-in-up overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="relative overflow-hidden bg-gradient-to-bl from-brand-700 via-brand-600 to-cyan-500 px-5 py-6 text-white sm:px-6">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-16 left-0 size-48 rounded-full bg-white/15 blur-2xl"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -bottom-24 right-0 size-56 rounded-full bg-cyan-300/25 blur-3xl"
          />
          <div className="relative flex items-start gap-4">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white/15 ring-1 ring-inset ring-white/25 backdrop-blur-sm">
              <PencilIcon className="size-6" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-medium tracking-wide text-white/70">گردش مالی · اصلاح پرداخت</p>
              <h1 className="mt-0.5 text-xl font-bold tracking-tight sm:text-2xl">اصلاح پرداخت</h1>
              <p className="mt-1.5 max-w-2xl text-sm leading-6 text-white/85">
                پرداخت اصلی حذف نمی‌شود؛ تخصیص‌های آن برگشت می‌خورند و یک پرداخت اصلاحی جدید ثبت می‌شود.
              </p>
            </div>
          </div>
        </div>

        {correctionBlockedReason ? (
          <div className="p-5 sm:p-6">
            <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 shadow-xs">
              <AlertTriangleIcon className="mt-0.5 size-5 shrink-0" />
              <p className="leading-6">{correctionBlockedReason}</p>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5 p-5 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-brand-600 ring-1 ring-brand-100">
                  <CreditCardIcon className="size-5" />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-800">
                    پرداخت #{toPersianDigits(payment.id)} — {payment.driver_name}
                  </p>
                  <p className="truncate text-xs text-slate-500">
                    {payment.driver_code} · دریافت: {formatJalaliShort(payment.payment_date)}
                    {payment.receipt_number ? ` · رسید ${payment.receipt_number}` : ''}
                  </p>
                </div>
              </div>
              <span className="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-xs ring-1 ring-slate-200">
                مبلغ فعلی: {toPersianDigits(payment.amount)} AFN
              </span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <ChangePreview
                label="مبلغ (AFN)"
                before={`${toPersianDigits(payment.amount)} AFN`}
                after={`${toPersianDigits(form.amount || payment.amount)} AFN`}
                changed={amountChanged}
              />
              <ChangePreview
                label="تاریخ پرداخت"
                before={formatJalaliShort(payment.payment_date)}
                after={formatJalaliShort(form.paymentDate || payment.payment_date)}
                changed={dateChanged}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="دلیل اصلاح" required className="sm:col-span-2">
                <input
                  className={inputClass}
                  required
                  value={form.reason}
                  onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))}
                  placeholder="دلیل اصلاح را ثبت کنید"
                />
              </Field>
              <Field label="مبلغ اصلاح‌شده (AFN)" required>
                <input
                  className={inputClass}
                  type="number"
                  inputMode="numeric"
                  min="1"
                  step="1"
                  required
                  value={form.amount}
                  onChange={(event) => setForm((current) => ({ ...current, amount: event.target.value }))}
                />
              </Field>
              <Field label="تاریخ پرداخت اصلاح‌شده" required>
                <input
                  className={inputClass}
                  type="date"
                  required
                  value={form.paymentDate}
                  onChange={(event) => setForm((current) => ({ ...current, paymentDate: event.target.value }))}
                />
              </Field>
            </div>

            <div className="flex items-start gap-3 rounded-2xl border border-brand-200 bg-brand-50 p-4 text-sm text-brand-800">
              <InfoIcon className="mt-0.5 size-4 shrink-0" />
              <p className="leading-6">
                دوره‌های تخصیص از پرداخت اصلی حفظ می‌شوند و با مبلغ جدید دوباره محاسبه خواهند شد.
                علت اصلاح و کاربر انجام‌دهنده نیز در سابقه پرداخت ثبت می‌شود.
              </p>
            </div>

            {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}

            <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5">
              <Button type="submit" loading={submitting} icon={<CheckIcon className="size-4" />}>
                ثبت اصلاح
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setForm({ reason: '', amount: payment.amount, paymentDate: payment.payment_date })}
              >
                بازگردانی مقادیر
              </Button>
            </div>
          </form>
        )}
      </section>
    </div>
  )
}

function ChangePreview({
  label,
  before,
  after,
  changed,
}: {
  label: string
  before: string
  after: string
  changed: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border p-4 transition-colors duration-200',
        changed ? 'border-brand-200 bg-brand-50/60' : 'border-slate-200 bg-slate-50/60',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        {changed && (
          <span className="rounded-full bg-brand-600/10 px-2 py-0.5 text-[11px] font-semibold text-brand-700">
            تغییر یافته
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span className={cn('text-slate-500', changed && 'line-through decoration-slate-400')}>
          {before}
        </span>
        <ArrowRightIcon className="size-4 shrink-0 rotate-180 text-slate-400" />
        <span className={cn('font-semibold', changed ? 'text-brand-700' : 'text-slate-800')}>
          {after}
        </span>
      </div>
    </div>
  )
}
