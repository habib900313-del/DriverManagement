import type { PaymentListItem } from '../types/financial'

type PaymentCorrectionEligibility = Pick<PaymentListItem, 'status'> & {
  refunds?: unknown
}

const PAYMENT_STATUS_LABELS: Record<string, string> = {
  received: 'دریافت‌شده',
  corrected: 'اصلاح‌شده',
  voided: 'ابطال‌شده',
}

export function getPaymentCorrectionDisabledReason(
  payment: PaymentCorrectionEligibility,
): string | null {
  if (!Array.isArray(payment.refunds)) {
    return 'سوابق برگشت پول قابل بررسی نیست؛ اصلاح این پرداخت ممکن نیست.'
  }
  if (payment.refunds.length > 0) {
    return 'این پرداخت سابقه برگشت پول دارد و قابل اصلاح نیست.'
  }
  if (payment.status !== 'received') {
    const status = PAYMENT_STATUS_LABELS[payment.status] ?? payment.status
    return `فقط پرداخت دریافت‌شده قابل اصلاح است؛ وضعیت فعلی: ${status}.`
  }
  return null
}
