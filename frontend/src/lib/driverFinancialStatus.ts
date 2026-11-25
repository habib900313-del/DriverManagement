import type { DriverFinancialSummary } from '../types/financial'

export type DriverFinancialStatus = 'overdue' | 'debtor' | 'paid' | 'unknown'

type FinancialAmounts = Pick<
  DriverFinancialSummary,
  'overdue_debt' | 'driver_total_balance'
>

export function parseMoney(
  value: string | null | undefined,
): number | null {
  if (value === null || value === undefined || value.trim() === '') return null
  const amount = Number(value)
  return Number.isFinite(amount) ? amount : null
}

/**
 * Classify a driver using only the existing ledger summary:
 *
 * 1. overdue  — overdue_debt > 0 (a subset of the total balance).
 * 2. debtor   — no overdue debt but a positive total balance, regardless of
 *               whether that balance belongs to the current period.
 * 3. paid     — total balance is zero. Available credit does not make a
 *               settled driver a debtor.
 * 4. unknown  — either required financial amount is invalid.
 */
export function getDriverFinancialStatus(
  summary: FinancialAmounts,
): DriverFinancialStatus {
  const overdueDebt = parseMoney(summary.overdue_debt)
  const totalBalance = parseMoney(summary.driver_total_balance)
  if (overdueDebt === null || totalBalance === null) return 'unknown'
  if (overdueDebt > 0) return 'overdue'
  if (totalBalance > 0) return 'debtor'
  return 'paid'
}

const STATUS_LABELS: Record<DriverFinancialStatus, string> = {
  overdue: 'معوق',
  debtor: 'بدهکار',
  paid: 'تسویه‌شده',
  unknown: 'نامشخص',
}

export function getDriverFinancialStatusLabel(
  summary: FinancialAmounts,
): string {
  return STATUS_LABELS[getDriverFinancialStatus(summary)]
}

export interface DriverFinancialStatusStyle {
  badge: string
  dot: string
  row: string
  legend: string
  description: string
}

export const DRIVER_FINANCIAL_STATUS_STYLES: Record<
  DriverFinancialStatus,
  DriverFinancialStatusStyle
> = {
  overdue: {
    badge: 'border-amber-300 bg-white text-amber-800',
    dot: 'bg-amber-500',
    row: 'bg-amber-200/70 hover:bg-amber-300/60',
    legend: 'معوق',
    description: 'بدهی دوره‌های گذشته',
  },
  debtor: {
    badge: 'border-rose-300 bg-white text-rose-700',
    dot: 'bg-rose-500',
    row: 'bg-rose-200/70 hover:bg-rose-300/60',
    legend: 'بدهکار',
    description: 'مانده بدهی بدون معوقه',
  },
  paid: {
    badge: 'border-emerald-300 bg-white text-emerald-700',
    dot: 'bg-emerald-500',
    row: 'bg-emerald-200/70 hover:bg-emerald-300/60',
    legend: 'تسویه‌شده',
    description: 'بدون بدهی باقیمانده',
  },
  unknown: {
    badge: 'border-slate-300 bg-white text-slate-600',
    dot: 'bg-slate-400',
    row: 'bg-slate-50 hover:bg-slate-100',
    legend: 'نامشخص',
    description: 'اطلاعات مالی معتبر در دسترس نیست',
  },
}
