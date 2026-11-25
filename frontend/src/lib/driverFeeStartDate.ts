import { isValidIsoDate } from './dates.ts'

export interface FeeStartDateChangeErrors {
  date?: string
  reason?: string
}

export function isFeeStartDateChanged(
  current: string,
  requested: string,
): boolean {
  return current.trim() !== requested.trim()
}

/**
 * Client-side validation for the W10 fee-start-date change.
 *
 * Only runs when the date actually changes; the backend still validates the
 * date and requires a non-blank reason. Changing the date never rewrites
 * existing payments — the backend anchors the new era after the current
 * period.
 */
export function validateFeeStartDateChange(
  current: string,
  requested: string,
  reason: string,
): FeeStartDateChangeErrors {
  const errors: FeeStartDateChangeErrors = {}
  if (!isFeeStartDateChanged(current, requested)) return errors

  if (
    !isValidIsoDate(requested) ||
    requested < '1900-01-01' ||
    requested > '2100-12-31'
  ) {
    errors.date = 'تاریخ شروع فیس باید یک تاریخ معتبر بین ۱۹۰۰ و ۲۱۰۰ باشد.'
  }
  if (!reason.trim()) {
    errors.reason = 'دلیل تغییر تاریخ شروع فیس الزامی است.'
  }
  return errors
}
