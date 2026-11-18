import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildFinancialReportCsv } from './financialReportExport.ts'

function report(archiveStatus, driverCode, fullName) {
  return {
    as_of: '2026-11-16',
    date_from: null,
    date_to: null,
    archive_status: archiveStatus,
    payments: { count: 1, total_amount: '600.00' },
    revenue: { cash_revenue: '600.00', recorded_as_of_audit: '600.00' },
    debt: {
      total_balance: '1800.00',
      current_obligation: '600.00',
      overdue_debt: '1200.00',
      fee_in_range: '2400.00',
    },
    credit: { available_total: '0.00', allocated_total: '0.00' },
    totals: { driver_count: 1, drivers_conserving: 1 },
    drivers: [
      {
        driver_id: 1,
        driver_code: driverCode,
        full_name: fullName,
        payments_count: 1,
        payments_total: '600.00',
        total_balance: '1800.00',
        current_obligation: '600.00',
        overdue_debt: '1200.00',
        available_credit: '0.00',
        credit_allocated: '0.00',
        fee_in_range: '2400.00',
        conservation_ok: true,
      },
    ],
  }
}

test('CSV export uses the active report filter and its driver rows', () => {
  const csv = buildFinancialReportCsv(
    report('active', 'ACTIVE-1', 'راننده فعال'),
  )

  assert.match(csv, /رانندگان فعال/)
  assert.match(csv, /ACTIVE-1/)
  assert.doesNotMatch(csv, /ARCHIVED-1/)
})

test('CSV export labels archived-only reports and escapes formula-like cells', () => {
  const csv = buildFinancialReportCsv(
    report('archived', '=ARCHIVED-1', 'راننده آرشیف‌شده'),
  )

  assert.match(csv, /رانندگان آرشیف‌شده/)
  assert.match(csv, /'=ARCHIVED-1/)
})
