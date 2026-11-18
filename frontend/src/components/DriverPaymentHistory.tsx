import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, LinkButton } from './ui/Button'
import { Pagination } from './ui/Pagination'
import { fetchPayments } from '../lib/api'
import { getPaymentCorrectionDisabledReason } from '../lib/payments'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { PaymentListItem } from '../types/financial'

const PAGE_SIZE = 25

function paymentStatusLabel(status: string) {
  if (status === 'received') return 'دریافت‌شده'
  if (status === 'corrected') return 'اصلاح‌شده'
  if (status === 'voided') return 'ابطال‌شده'
  return status
}

export function DriverPaymentHistory({
  driverId,
  canManage,
}: {
  driverId: number
  canManage: boolean
}) {
  const [result, setResult] = useState<{
    key: string
    payments: PaymentListItem[]
    count: number
    error: string | null
  } | null>(null)
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const queryKey = `${driverId}:${page}:${retry}`

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    fetchPayments(
      { driver_id: driverId, page, page_size: PAGE_SIZE },
      controller.signal,
    )
      .then((response) => {
        if (!Array.isArray(response.results) || typeof response.count !== 'number') {
          throw new Error('پاسخ سوابق پرداخت معتبر نیست.')
        }
        if (active) {
          setResult({
            key: queryKey,
            payments: response.results,
            count: response.count,
            error: null,
          })
        }
      })
      .catch((cause) => {
        if (active && !isAbortError(cause)) {
          setResult({
            key: queryKey,
            payments: [],
            count: 0,
            error: getErrorMessage(cause),
          })
        }
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [driverId, page, queryKey, retry])

  const currentResult = result?.key === queryKey ? result : null
  const loading = currentResult === null
  const error = currentResult?.error ?? null
  const payments = currentResult?.payments ?? []
  const count = currentResult?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  return (
    <section className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-800">تاریخچه پرداخت‌های راننده</h2>
        <Link
          to={`/financial/history?driver_id=${driverId}`}
          className="text-xs font-medium text-slate-600 hover:text-slate-900"
        >
          همه سوابق پرداخت
        </Link>
      </div>

      {loading ? (
        <p className="p-5 text-center text-sm text-slate-500">در حال دریافت سوابق پرداخت…</p>
      ) : error ? (
        <div className="flex flex-wrap items-center justify-between gap-3 p-4" role="alert">
          <p className="text-sm text-rose-700">{error}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setRetry((value) => value + 1)}
          >
            تلاش دوباره
          </Button>
        </div>
      ) : payments.length === 0 ? (
        <p className="p-5 text-sm text-slate-500">برای این راننده پرداختی ثبت نشده است.</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-2 text-right font-medium">پرداخت</th>
                  <th className="px-4 py-2 text-right font-medium">تاریخ</th>
                  <th className="px-4 py-2 text-right font-medium" dir="ltr">مبلغ</th>
                  <th className="px-4 py-2 text-right font-medium">وضعیت</th>
                  <th className="px-4 py-2 text-right font-medium">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {payments.map((payment) => {
                  const blockedReason = getPaymentCorrectionDisabledReason(payment)
                  return (
                    <tr key={payment.id} className="align-top hover:bg-slate-50/70">
                      <td className="px-4 py-3">
                        <Link
                          to={`/financial/payments/${payment.id}`}
                          className="font-medium text-brand-700 hover:underline"
                        >
                          پرداخت #{toPersianDigits(payment.id)}
                        </Link>
                        {payment.receipt_number && (
                          <p className="mt-1 text-xs text-slate-500">
                            رسید: {payment.receipt_number}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-600">
                        {formatJalaliShort(payment.payment_date)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-700" dir="ltr">
                        {toPersianDigits(payment.amount)} AFN
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-600">
                        {paymentStatusLabel(payment.status)}
                        {Number(payment.refunded_total) > 0 && (
                          <p className="mt-1 text-rose-600">
                            برگشت‌شده: {toPersianDigits(payment.refunded_total)} AFN
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-start gap-2">
                          <LinkButton
                            to={`/financial/payments/${payment.id}`}
                            variant="secondary"
                            size="sm"
                          >
                            جزئیات
                          </LinkButton>
                          {canManage &&
                            (blockedReason ? (
                              <div className="max-w-64">
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  disabled
                                  title={blockedReason}
                                  aria-label={`اصلاح پرداخت غیرفعال: ${blockedReason}`}
                                >
                                  اصلاح پرداخت
                                </Button>
                                <p className="mt-1 text-[11px] leading-5 text-amber-700">
                                  {blockedReason}
                                </p>
                              </div>
                            ) : (
                              <LinkButton
                                to={`/financial/payments/${payment.id}/correct`}
                                variant="secondary"
                                size="sm"
                              >
                                اصلاح پرداخت
                              </LinkButton>
                            ))}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            onChange={setPage}
          />
        </>
      )}
    </section>
  )
}
