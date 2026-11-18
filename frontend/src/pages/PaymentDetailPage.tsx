import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button, LinkButton } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { useAuth } from '../context/AuthContext'
import { fetchPayment } from '../lib/api'
import { formatJalaliShort, formatKabulDateTime, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import { getPaymentCorrectionDisabledReason } from '../lib/payments'
import type { PaymentListItem } from '../types/financial'

function paymentStatusLabel(status: string) {
  if (status === 'received') return 'دریافت‌شده'
  if (status === 'corrected') return 'اصلاح‌شده'
  if (status === 'voided') return 'ابطال‌شده'
  return status
}

export function PaymentDetailPage() {
  const { id } = useParams()
  const paymentId = Number(id)
  const { user } = useAuth()
  const [payment, setPayment] = useState<PaymentListItem | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!Number.isInteger(paymentId) || paymentId <= 0) {
      return
    }

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

  const isLoading = loading || (!error && payment?.id !== paymentId)
  const retryLoad = () => {
    setError(null)
    setLoading(true)
    setRetry((value) => value + 1)
  }

  if (!Number.isInteger(paymentId) || paymentId <= 0) {
    return <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 shadow-xs">شناسه پرداخت معتبر نیست.</p>
  }

  if (isLoading) {
    return <p className="p-8 text-center text-sm text-slate-500">در حال بارگذاری جزئیات پرداخت…</p>
  }

  if (error || !payment) {
    return (
      <div className="space-y-4 rounded-xl border border-rose-200 bg-rose-50 p-6 text-center">
        <p className="text-sm text-rose-700">{error || 'پرداخت یافت نشد.'}</p>
        <Button variant="secondary" size="sm" onClick={retryLoad}>
          تلاش دوباره
        </Button>
      </div>
    )
  }

  const canManage = Boolean(user?.is_staff || user?.is_superuser)
  const correctionBlockedReason = getPaymentCorrectionDisabledReason(payment)

  return (
    <div className="space-y-5">
      <Link to="/financial/history" className="text-sm font-medium text-slate-600 hover:text-slate-900">
        بازگشت به سوابق پرداخت
      </Link>
      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <PageHeader
          title={`جزئیات پرداخت #${toPersianDigits(payment.id)}`}
          description="سوابق اصلی، اصلاحات و تخصیص‌های مالی پرداخت"
          actions={
            canManage && payment.status === 'received' ? (
              <div className="flex flex-wrap gap-2">
                {correctionBlockedReason ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled
                    title={correctionBlockedReason}
                  >
                    اصلاح پرداخت
                  </Button>
                ) : (
                  <LinkButton size="sm" to={`/financial/payments/${payment.id}/correct`}>
                    اصلاح پرداخت
                  </LinkButton>
                )}
                {Number(payment.refundable_amount) > 0 && (
                  <LinkButton
                    size="sm"
                    variant="danger"
                    to={`/financial/payments/${payment.id}/refund`}
                  >
                    برگشت پول
                  </LinkButton>
                )}
              </div>
            ) : undefined
          }
        />
        <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
          <Detail label="راننده">
            <Link className="text-brand-700 hover:underline" to={`/financial/drivers/${payment.driver}`}>
              {payment.driver_code} — {payment.driver_name}
            </Link>
          </Detail>
          <Detail label="مبلغ">{toPersianDigits(payment.amount)} AFN</Detail>
          <Detail label="تاریخ پرداخت">{formatJalaliShort(payment.payment_date)}</Detail>
          <Detail label="وضعیت">{paymentStatusLabel(payment.status)}</Detail>
          <Detail label="شماره رسید">{payment.receipt_number || '—'}</Detail>
          <Detail label="توضیحات">{payment.description || '—'}</Detail>
          {payment.correction_of && (
            <Detail label="پرداخت جایگزین">
              <Link className="text-brand-700 hover:underline" to={`/financial/payments/${payment.correction_of}`}>
                پرداخت اصلی #{toPersianDigits(payment.correction_of)}
              </Link>
            </Detail>
          )}
          {payment.status === 'corrected' && (
            <>
              <Detail label="زمان اصلاح">
                {payment.corrected_at ? formatKabulDateTime(payment.corrected_at) : '—'}
              </Detail>
              <Detail label="اصلاح‌کننده">{payment.corrected_by_name || '—'}</Detail>
              <Detail label="دلیل اصلاح">{payment.correction_reason || '—'}</Detail>
            </>
          )}
        </div>

        <div className="border-t border-slate-100 p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-800">سوابق برگشت پول</h2>
          {!Array.isArray(payment.refunds) || payment.refunds.length === 0 ? (
            <p className="mb-5 text-sm text-slate-500">برگشت پولی برای این پرداخت ثبت نشده است.</p>
          ) : (
            <div className="mb-5 space-y-3">
              {payment.refunds.map((refund) => (
                <div key={refund.id} className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm shadow-xs">
                  <div className="flex flex-wrap justify-between gap-2">
                    <span>{formatJalaliShort(refund.refund_date)}</span>
                    <span className="font-mono">{toPersianDigits(refund.amount)} AFN</span>
                  </div>
                  <p className="mt-1 text-slate-700">{refund.reason}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    ثبت‌کننده: {refund.refunded_by_name} — اثر از {formatJalaliShort(refund.effective_date)}
                  </p>
                </div>
              ))}
            </div>
          )}
          {canManage && correctionBlockedReason && (
            <p className="mb-5 text-sm text-amber-700" role="status">
              اصلاح پرداخت در دسترس نیست: {correctionBlockedReason}
            </p>
          )}
          <p className="mb-5 text-sm text-slate-600">
            برگشت‌شده: {toPersianDigits(payment.refunded_total)} AFN؛
            قابل‌برگشت: {toPersianDigits(payment.refundable_amount)} AFN
          </p>

          <h2 className="mb-3 text-sm font-semibold text-slate-800">تخصیص‌ها و سوابق reversal</h2>
          {payment.allocations.length === 0 ? (
            <p className="text-sm text-slate-500">تخصیصی برای این پرداخت ثبت نشده است.</p>
          ) : (
            <div className="space-y-3">
              {payment.allocations.map((allocation) => (
                <div key={allocation.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                  <div className="flex flex-wrap justify-between gap-2">
                    <span>
                      {allocation.target_period_start && allocation.target_period_end
                        ? `${formatJalaliShort(allocation.target_period_start)} تا ${formatJalaliShort(allocation.target_period_end)}`
                        : allocation.allocation_type}
                    </span>
                    <span className="font-mono">{toPersianDigits(allocation.allocated_amount)} AFN</span>
                  </div>
                  {allocation.is_reversed && (
                    <p className="mt-2 text-xs text-rose-700">
                      برگشت‌شده{allocation.reversal_reason ? `: ${allocation.reversal_reason}` : ''}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <div className="mt-1 text-sm font-medium text-slate-800">{children}</div>
    </div>
  )
}
