export interface PeriodState {
  start: string
  end: string
  due_date: string
  is_overdue: boolean
  fee: string
  remaining_own: string
  balance: string
  reductions: string
  cash_settled: string
  credit_settled: string
  net_waiver: string
  net_transfer_out: string
  net_transfer_in: string
  transfers: PeriodTransfer[]
}

export interface PeriodTransfer {
  adjustment_id: number
  effective_date: string
  original_amount: string
  reversed_total: string
  net: string
  remaining: string
}

export interface DriverFinancialSummary {
  driver_id: number
  as_of: string
  current_obligation: string
  overdue_debt: string
  driver_total_balance: string
  available_credit: string
  cash_received: string
  periods: PeriodState[]
}

export interface ConservationEquation {
  [key: string]: ConservationEquationMetric
}

export interface ConservationEquationMetric {
  [key: string]: string | boolean
  ok: boolean
}

export interface ConservationReport {
  driver_id: number
  as_of: string
  all_ok: boolean
  equations: ConservationEquation
  payments: PaymentCheck[]
  credit_sources: CreditSourceCheck[]
  reversals: ReversalCheck[]
}

export interface PaymentCheck {
  payment_id: number
  amount: string
  fee_allocated: string
  credit_allocated: string
  unallocated: string
  cap_ok: boolean
  partition_ok: boolean
}

export interface CreditSourceCheck {
  allocation_id: number
  allocated: string
  consumed: string
  available: string
  ok: boolean
}

export interface ReversalCheck {
  adjustment_id: number
  original_amount: string
  reversed_total: string
  ok: boolean
}

export interface CashRevenueReport {
  as_of: string
  date_from: string | null
  date_to: string | null
  cash_revenue: string
  recorded_as_of_audit: string
  payment_count: number
  driver_count: number
  by_month: CashRevenueMonthRow[]
}

export interface FinancialReportDriverRow {
  driver_id: number
  driver_code: string
  full_name: string
  payments_count: number
  payments_total: string
  total_balance: string
  current_obligation: string
  overdue_debt: string
  available_credit: string
  credit_allocated: string
  fee_in_range: string
  conservation_ok: boolean
}

export interface PeriodAllocationDetail {
  id: number
  payment_id: number
  amount: string
  effective_date: string
  payment_date: string
  receipt_number: string
  description: string
  payment_amount: string
  reversed_at: string | null
  reversal_reason: string
}

export interface PeriodConsumptionDetail {
  id: number
  amount: string
  effective_date: string
  source_allocation_id: number
  reason: string
  reversed_at: string | null
}

export interface PeriodCoverageRow {
  start: string
  end: string
  due_date: string
  total: string
  paid: string
  remaining: string
  percent: number
  status: 'paid' | 'partial' | 'unpaid'
  is_overdue: boolean
  is_current: boolean
  is_future: boolean
  allocations: PeriodAllocationDetail[]
  consumptions: PeriodConsumptionDetail[]
}

export interface DriverPeriodCoverage {
  driver_id: number
  as_of: string
  periods: PeriodCoverageRow[]
}

export interface CashRevenueMonthRow {
  month: string
  total: string
  count: number
}

export type FinancialReportArchiveStatus = 'active' | 'archived' | 'all'

export interface FinancialReport {
  as_of: string
  date_from: string | null
  date_to: string | null
  archive_status: FinancialReportArchiveStatus
  payments: { count: number; total_amount: string }
  revenue: { cash_revenue: string; recorded_as_of_audit: string }
  debt: {
    total_balance: string
    current_obligation: string
    overdue_debt: string
    fee_in_range: string
  }
  credit: { available_total: string; allocated_total: string }
  drivers: FinancialReportDriverRow[]
  totals: { driver_count: number; drivers_conserving: number }
}

export interface PeriodBounds {
  start: string
  end: string
}

export interface DriverPeriodsResponse {
  driver_id: number
  fee_start_date: string
  periods: (PeriodBounds & { fee?: string })[]
}

export interface PaymentListParams {
  driver_id?: number
  date_from?: string
  date_to?: string
  search?: string
  page?: number
  page_size?: number
}

export interface DriverFeeHistoryItem {
  id: number
  driver: number
  old_fee_start_date: string | null
  requested_fee_start_date: string
  effective_fee_start_date: string
  reason: string
  changed_by: number
  changed_by_name: string
  changed_at: string
}

export interface ReasonInput {
  reason: string
}

export interface ReceivePaymentInput {
  driver_id: number
  amount: string
  payment_date: string
  target_period_start?: string | null
  target_period_end?: string | null
  receipt_number?: string
  description?: string
  idempotency_key?: string
}

export interface ConsumeCreditInput {
  source_allocation_id: number
  amount: string
  target_period_start: string
  target_period_end: string
  consumption_id?: string
  reason?: string
}

export interface AdjustmentInput {
  driver_id: number
  adjustment_type: 'waiver' | 'transfer'
  amount: string
  source_period_start: string
  source_period_end: string
  destination_period_start?: string | null
  destination_period_end?: string | null
  reason: string
}

export interface ReverseAdjustmentInput {
  amount: string
  reason: string
}

export interface FeeScheduleInput {
  amount: string
  effective_from: string
  reason: string
}

export interface FeeStartDateInput {
  requested_fee_start_date: string
  reason: string
}

export interface CorrectPaymentInput {
  reason: string
  new_amount?: string | null
  new_driver_id?: number | null
  new_payment_date?: string | null
  target_period_start?: string | null
  target_period_end?: string | null
}

export interface CorrectAllocationInput {
  reason: string
  new_target_period_start: string
  new_target_period_end: string
}

export interface CorrectCreditInput {
  reason: string
  new_credit_amount: string
  fee_allocations: Array<{
    start: string
    end: string
    amount: string
  }>
  consumptions: Array<{
    start: string
    end: string
    amount: string
  }>
}

export interface PaymentListItem {
  id: number
  driver: number
  driver_code: string
  driver_name: string
  amount: string
  payment_date: string
  effective_date: string
  receipt_number: string
  description: string
  idempotency_key: string | null
  status: string
  is_void: boolean
  correction_of: number | null
  void_reason: string
  correction_reason: string
  voided_at: string | null
  corrected_at: string | null
  corrected_by: number | null
  corrected_by_name: string | null
  created_by: number
  created_at: string
  updated_at: string
  allocations: PaymentAllocationListItem[]
  refunds: PaymentRefundListItem[]
  refunded_total: string
  refundable_amount: string
}

export interface PaymentRefundListItem {
  id: number
  payment: number
  amount: string
  refund_date: string
  effective_date: string
  reason: string
  refunded_by: number
  refunded_by_name: string
  created_at: string
}

export interface PaymentRefundInput {
  amount: string
  refund_date: string
  reason: string
}

export interface PaymentAllocationListItem {
  id: number
  payment: number
  allocation_type: string
  target_period_start: string | null
  target_period_end: string | null
  allocated_amount: string
  effective_date: string
  correction_of: number | null
  reversed_at: string | null
  reversal_reason: string
  is_reversed: boolean
  allocated_by: number
  created_at: string
  consumptions: AllocationConsumptionListItem[]
}

export interface AllocationConsumptionListItem {
  id: number
  source_allocation: number
  consumption_amount: string
  target_period_start: string
  target_period_end: string
  effective_date: string
  consumption_id: string
  consumed_by: number
  consumed_by_name: string
  reason: string
  reversed_at: string | null
  reversal_reason: string
  is_reversed: boolean
  consumed_at: string
}

export interface AdjustmentListItem {
  id: number
  driver: number
  adjustment_type: string
  type_label: string
  amount: string
  source_period_start: string
  source_period_end: string
  destination_period_start: string | null
  destination_period_end: string | null
  reverses_adjustment: number | null
  reason: string
  effective_date: string
  created_by: number
  created_at: string
}

export interface FeeScheduleListItem {
  id: number
  amount: string
  effective_from: string
  reason: string
  created_by: number
  created_at: string
}

export interface DriverFeeHistoryListItem {
  id: number
  driver: number
  old_fee_start_date: string | null
  requested_fee_start_date: string
  effective_fee_start_date: string
  reason: string
  changed_by: number
  changed_by_name: string
  changed_at: string
}

export type FinancialViewMode = 'summary' | 'payments' | 'periods' | 'credit' | 'transfers' | 'history' | 'reports'

export interface AFNAmount {
  value: string
  formatted: string
}