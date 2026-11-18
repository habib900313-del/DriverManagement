import {
  isValidJalaaliDate,
  jalaaliMonthLength,
  toGregorian,
  toJalaali,
} from 'jalaali-js'

export const KABUL_TIME_ZONE = 'Asia/Kabul'

export const JALALI_MONTHS = [
  'حمل',
  'ثور',
  'جوزا',
  'سرطان',
  'اسد',
  'سنبله',
  'میزان',
  'عقرب',
  'قوس',
  'جدی',
  'دلو',
  'حوت',
] as const

export const WEEKDAY_LABELS = [
  'شنبه',
  'یکشنبه',
  'دوشنبه',
  'سه‌شنبه',
  'چهارشنبه',
  'پنجشنبه',
  'جمعه',
] as const

const PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

export function toPersianDigits(value: string | number): string {
  return String(value).replace(/[0-9]/g, (digit) => PERSIAN_DIGITS[Number(digit)])
}

export function todayIsoKabul(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: KABUL_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())

  const pick = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? ''

  return `${pick('year')}-${pick('month')}-${pick('day')}`
}

export function isValidIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  if (month < 1 || month > 12 || day < 1 || day > 31) return false
  const date = new Date(Date.UTC(year, month - 1, day))
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  )
}

/**
 * Validate a report date range. Empty bounds mean "no filter"; ISO dates
 * compare correctly as strings. ``asOf`` is an optional inclusive upper bound.
 * Returns a Persian validation message, or ``null`` when the range is valid.
 */
export function validateDateRange(
  from: string,
  to: string,
  asOf?: string,
): string | null {
  if (from && to && from > to) {
    return 'تاریخ شروع نباید بعد از تاریخ پایان باشد.'
  }
  if (to && asOf && to > asOf) {
    return 'تاریخ پایان نباید بعد از تاریخ محاسبه باشد.'
  }
  return null
}

function addGregorianMonths(value: string, months: number): string | null {
  if (!isValidIsoDate(value)) return null
  const [year, month, day] = value.split('-').map(Number)
  const totalMonths = year * 12 + month - 1 + months
  const targetYear = Math.floor(totalMonths / 12)
  const targetMonth = (totalMonths % 12) + 1
  const lastDay = new Date(Date.UTC(targetYear, targetMonth, 0)).getUTCDate()
  return `${targetYear}-${pad2(targetMonth)}-${pad2(Math.min(day, lastDay))}`
}

export function isValidQuarterPeriod(
  anchor: string,
  start: string,
  end: string,
): boolean {
  if (!isValidIsoDate(anchor) || !isValidIsoDate(start) || !isValidIsoDate(end)) {
    return false
  }

  const [anchorYear, anchorMonth] = anchor.split('-').map(Number)
  const [startYear, startMonth] = start.split('-').map(Number)
  const monthOffset = (startYear - anchorYear) * 12 + startMonth - anchorMonth
  if (monthOffset < 0 || monthOffset % 3 !== 0) return false

  const expectedStart = addGregorianMonths(anchor, monthOffset)
  const nextStart = addGregorianMonths(anchor, monthOffset + 3)
  if (!expectedStart || !nextStart || expectedStart !== start) return false

  const nextDate = new Date(`${nextStart}T00:00:00Z`)
  nextDate.setUTCDate(nextDate.getUTCDate() - 1)
  const expectedEnd = `${nextDate.getUTCFullYear()}-${pad2(
    nextDate.getUTCMonth() + 1,
  )}-${pad2(nextDate.getUTCDate())}`
  return end === expectedEnd
}

export function addJalaliMonths(value: string, months: number): string | null {
  const jalali = isoToJalali(value)
  if (!jalali || !Number.isInteger(months)) return null
  const target = shiftJalaliMonth(jalali.jy, jalali.jm, months)
  const day = Math.min(
    jalali.jd,
    jalaaliMonthLength(target.jy, target.jm),
  )
  return jalaliToIso(target.jy, target.jm, day)
}

export function jalaliQuarterEnd(start: string): string | null {
  const nextStart = addJalaliMonths(start, 3)
  if (!nextStart) return null
  const [year, month, day] = nextStart.split('-').map(Number)
  const end = new Date(Date.UTC(year, month - 1, day - 1))
  return `${end.getUTCFullYear()}-${pad2(end.getUTCMonth() + 1)}-${pad2(
    end.getUTCDate(),
  )}`
}

export function isValidJalaliQuarterPeriod(
  anchor: string,
  start: string,
  end: string,
): boolean {
  const anchorDate = isoToJalali(anchor)
  const startDate = isoToJalali(start)
  if (!anchorDate || !startDate || !isValidIsoDate(end)) return false

  const monthOffset =
    (startDate.jy - anchorDate.jy) * 12 + startDate.jm - anchorDate.jm
  if (monthOffset < 0 || monthOffset % 3 !== 0) return false

  return (
    addJalaliMonths(anchor, monthOffset) === start &&
    jalaliQuarterEnd(start) === end
  )
}

export interface JalaliDate {
  jy: number
  jm: number
  jd: number
}

export function isoToJalali(iso: string): JalaliDate | null {
  if (!isValidIsoDate(iso)) return null
  const [year, month, day] = iso.split('-').map(Number)
  try {
    return toJalaali(year, month, day)
  } catch {
    return null
  }
}

export function jalaliToIso(jy: number, jm: number, jd: number): string {
  const gregorian = toGregorian(jy, jm, jd)
  return `${gregorian.gy}-${pad2(gregorian.gm)}-${pad2(gregorian.gd)}`
}

export function isValidJalali(jy: number, jm: number, jd: number): boolean {
  try {
    return isValidJalaaliDate(jy, jm, jd)
  } catch {
    return false
  }
}

export function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

export function formatJalaliShort(iso: string): string {
  const jalali = isoToJalali(iso)
  if (!jalali) return '—'
  return toPersianDigits(
    `${jalali.jy}/${pad2(jalali.jm)}/${pad2(jalali.jd)}`,
  )
}

export function formatJalaliLong(iso: string): string {
  const jalali = isoToJalali(iso)
  if (!jalali) return '—'
  return toPersianDigits(
    `${jalali.jd} ${JALALI_MONTHS[jalali.jm - 1]} ${jalali.jy}`,
  )
}

export function formatGregorianShort(iso: string): string {
  if (!isValidIsoDate(iso)) return '—'
  return toPersianDigits(iso)
}

export function weekdayOfIso(iso: string): string {
  const jalali = isoToJalali(iso)
  if (!jalali) return '—'
  const gregorian = toGregorian(jalali.jy, jalali.jm, jalali.jd)
  const utcDate = new Date(
    Date.UTC(gregorian.gy, gregorian.gm - 1, gregorian.gd),
  )
  // JavaScript weeks start on Sunday; the Jalali week starts on Saturday.
  return WEEKDAY_LABELS[(utcDate.getUTCDay() + 1) % 7]
}

/** Leading blanks plus day numbers for a Jalali month, padded to full weeks. */
export function buildJalaliMonth(jy: number, jm: number): Array<number | null> {
  const length = jalaaliMonthLength(jy, jm)
  const first = toGregorian(jy, jm, 1)
  const firstWeekday = new Date(
    Date.UTC(first.gy, first.gm - 1, first.gd),
  ).getUTCDay()
  const offset = (firstWeekday + 1) % 7

  const cells: Array<number | null> = Array.from({ length: offset }, () => null)
  for (let day = 1; day <= length; day += 1) cells.push(day)
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
}

export function shiftJalaliMonth(
  jy: number,
  jm: number,
  delta: number,
): { jy: number; jm: number } {
  const total = jy * 12 + (jm - 1) + delta
  return { jy: Math.floor(total / 12), jm: (total % 12) + 1 }
}

export function currentJalaliYear(): number {
  return isoToJalali(todayIsoKabul())?.jy ?? 1400
}

export function jalaliYearOptions(span = 40): number[] {
  const current = currentJalaliYear()
  const years: number[] = []
  for (let year = current - span; year <= current + span; year += 1) {
    years.push(year)
  }
  return years
}

export interface KabulDateTime {
  dateIso: string
  time: string
}

export function toKabulDateTime(value: string): KabulDateTime | null {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null

  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: KABUL_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(date)

  const pick = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? ''

  return {
    dateIso: `${pick('year')}-${pick('month')}-${pick('day')}`,
    time: `${pick('hour')}:${pick('minute')}`,
  }
}

export function formatKabulDateTime(value: string): string {
  const parsed = toKabulDateTime(value)
  if (!parsed) return '—'
  return `${formatJalaliShort(parsed.dateIso)} — ${toPersianDigits(parsed.time)}`
}
