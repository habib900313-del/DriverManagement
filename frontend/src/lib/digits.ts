/** Shared digit normalization: Persian and Arabic digits → English digits. */

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
