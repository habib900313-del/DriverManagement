import { ApiError } from './api'

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'خطای نامشخصی رخ داد. دوباره تلاش کنید.'
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

const PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹'
const ARABIC_DIGITS = '٠١٢٣٤٥٦٧٨٩'

export function normalizeDigits(value: string): string {
  return value.replace(/[۰-۹٠-٩]/g, (digit) => {
    const persianIndex = PERSIAN_DIGITS.indexOf(digit)
    if (persianIndex >= 0) return String(persianIndex)
    const arabicIndex = ARABIC_DIGITS.indexOf(digit)
    return arabicIndex >= 0 ? String(arabicIndex) : digit
  })
}
