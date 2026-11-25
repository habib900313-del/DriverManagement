import { isValidIsoDate, jalaliQuarterEnd } from './dates.ts'

export interface FirstFeePeriod {
  start: string
  end: string
}

/**
 * The first fee period of a driver's era.
 *
 * Rule: the first period starts exactly on the driver's fee start date and
 * lasts one three-month (Jalali quarter) period. Subsequent periods keep the
 * existing anchor + 3 months grid, so this helper never changes them.
 *
 * Returns null when the fee start date is missing or invalid; callers must
 * show a validation error and must not substitute another date.
 */
export function deriveFirstFeePeriod(
  feeStartDate: string,
): FirstFeePeriod | null {
  if (
    !isValidIsoDate(feeStartDate) ||
    feeStartDate < '1900-01-01' ||
    feeStartDate > '2100-12-31'
  ) {
    return null
  }
  const end = jalaliQuarterEnd(feeStartDate)
  return end ? { start: feeStartDate, end } : null
}
