import type { PaymentListParams } from '../types/financial'

export const DEFAULT_PAGE_SIZE = 25

function toPage(value: number | undefined, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return fallback
  return Math.max(1, Math.trunc(value))
}

/**
 * Merge a partial list-param change into the current params.
 *
 * Changing anything other than the page (filters, search, page size) starts
 * from the first page, because the previous page number may no longer exist.
 * Changing only the page keeps the active filters and clamps the value to a
 * valid page (>= 1).
 */
export function applyListChange(
  current: PaymentListParams,
  next: Partial<PaymentListParams>,
): PaymentListParams {
  const changesFilters = Object.keys(next).some((key) => key !== 'page')
  if (changesFilters) {
    return { ...current, ...next, page: 1 }
  }

  return {
    ...current,
    ...next,
    page: toPage(next.page, current.page ?? 1),
  }
}

/**
 * Page to show after deleting a payment from `currentPage`.
 *
 * `itemsOnPage` is the number of rows rendered before the deletion. When the
 * deleted row was the last one on a page after the first, step back one page
 * so the list never shows an empty page.
 */
export function pageAfterDeletion(
  currentPage: number,
  itemsOnPage: number,
): number {
  const page = toPage(currentPage, 1)
  return itemsOnPage <= 1 && page > 1 ? page - 1 : page
}
