import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowRightIcon, RefreshIcon } from '../components/icons'
import { Button } from '../components/ui/Button'
import { Field, inputClass, textareaClass } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import { fetchPayment, refundPayment } from '../lib/api'
import { formatJalaliShort, todayIsoKabul, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { PaymentListItem } from '../types/financial'

export function PaymentRefundPage() {
  const { id } = useParams()
  const paymentId = Number(id)
  const navigate = useNavigate()
  const { notify } = useToast()
  const [payment, setPayment] = useState<PaymentListItem | null>(null)
  const [amount, setAmount] = useState('')
  const [refundDate, setRefundDate] = useState(todayIsoKabul())
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!Number.isInteger(paymentId) || paymentId <= 0) return

    const controller = new AbortController()
    fetchPayment(paymentId, controller.signal)
      .then(setPayment)
      .catch((cause) => {
        if (!isAbortError(cause)) setError(getErrorMessage(cause))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [paymentId, retry])

  const retryLoad = () => {
    setError(null)
    setLoading(true)
    setRetry((value) => value + 1)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!payment) return
    setSubmitting(true)
    setError(null)
    try {
      await refundPayment(payment.id, {
        amount,
        refund_date: refundDate,
        reason: reason.trim(),
      })
      notify('success', 'برگشت پول ثبت شد و تخصیص‌ها به‌روز شدند.')
      navigate(`/financial/payments/${payment.id}`)
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

  if (!Number.isInteger(paymentId) || paymentId <= 0) {
    return <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 shadow-xs">شناسه پرداخت معتبر نیست.</p>
  }

  const isLoading = loading || (!error && payment?.id !== paymentId)
  if (isLoading) {
    return <p className="p-8 text-center text-sm text-slate-500">در حال بارگذاری پرداخت…</p>
  }
  if (error || !payment) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <p className="text-sm text-rose-700">{error || 'پرداخت یافت نشد.'}</p>
        <Button variant="secondary" size="sm" onClick={retryLoad}>
          <RefreshIcon className="size-4" />
          تلاش دوباره
        </Button>
      </div>
    )
  }

  const refundableAmount = Number(payment.refundable_amount)
  const canRefund = payment.status === 'received' && refundableAmount > 0

  return (
    <div className="space-y-5">
      <Link
        to={`/financial/payments/${payment.id}`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowRightIcon className="size-4" />
        بازگشت به جزئیات پرداخت
      </Link>
      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <PageHeader
          title="برگشت پول"
          description="Refund به‌صورت مستقل ثبت می‌شود؛ پرداخت و سوابق قبلی حذف یا بازنویسی نمی‌شوند."
        />
        {!canRefund ? (
          <p className="p-5 text-sm text-amber-800">
            این پرداخت قابل برگشت نیست. مانده قابل‌برگشت: {toPersianDigits(payment.refundable_amount)} AFN
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5 p-5">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 shadow-xs">
              <p>پرداخت: #{toPersianDigits(payment.id)} — {payment.driver_name}</p>
              <p className="mt-1">مبلغ پرداخت: {toPersianDigits(payment.amount)} AFN</p>
              <p className="mt-1 font-semibold">
                قابل‌برگشت: {toPersianDigits(payment.refundable_amount)} AFN
              </p>
              <p className="mt-1">تاریخ پرداخت: {formatJalaliShort(payment.payment_date)}</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="مبلغ برگشت (AFN)" required>
                <input
                  className={inputClass}
                  type="number"
                  inputMode="numeric"
                  min="1"
                  max={refundableAmount}
                  step="1"
                  required
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                />
              </Field>
              <Field label="تاریخ برگشت" required>
                <input
                  className={inputClass}
                  type="date"
                  required
                  max={todayIsoKabul()}
                  value={refundDate}
                  onChange={(event) => setRefundDate(event.target.value)}
                />
              </Field>
              <Field label="دلیل برگشت" required className="sm:col-span-2">
                <textarea
                  className={textareaClass}
                  required
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="دلیل برگشت وجه را ثبت کنید"
                />
              </Field>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="submit"
                variant="danger"
                loading={submitting}
                disabled={!amount || Number(amount) <= 0 || Number(amount) > refundableAmount}
              >
                ثبت برگشت پول
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setAmount(payment.refundable_amount)}
              >
                برگشت کامل ({toPersianDigits(payment.refundable_amount)} AFN)
              </Button>
            </div>
            {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
          </form>
        )}
      </section>
    </div>
  )
}
