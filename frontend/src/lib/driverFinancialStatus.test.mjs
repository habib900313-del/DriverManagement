import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  DRIVER_FINANCIAL_STATUS_STYLES,
  getDriverFinancialStatus,
  getDriverFinancialStatusLabel,
  parseMoney,
} from './driverFinancialStatus.ts'

function summary(overrides = {}) {
  return {
    overdue_debt: '0.00',
    driver_total_balance: '0.00',
    ...overrides,
  }
}

test('overdue debt is labelled معوق and uses the amber row', () => {
  const row = summary({
    overdue_debt: '600.00',
    driver_total_balance: '1000.00',
  })
  assert.equal(getDriverFinancialStatus(row), 'overdue')
  assert.equal(getDriverFinancialStatusLabel(row), 'معوق')
  assert.match(DRIVER_FINANCIAL_STATUS_STYLES.overdue.row, /amber/)
})

test('a balance without overdue debt is labelled بدهکار and uses the rose row', () => {
  const row = summary({
    overdue_debt: '0.00',
    driver_total_balance: '400.00',
  })
  assert.equal(getDriverFinancialStatus(row), 'debtor')
  assert.equal(getDriverFinancialStatusLabel(row), 'بدهکار')
  assert.match(DRIVER_FINANCIAL_STATUS_STYLES.debtor.row, /rose/)
})

test('a current obligation does not become "در انتظار پرداخت"', () => {
  const row = summary({
    overdue_debt: '0.00',
    current_obligation: '400.00',
    driver_total_balance: '400.00',
  })
  assert.equal(getDriverFinancialStatus(row), 'debtor')
  assert.equal(getDriverFinancialStatusLabel(row), 'بدهکار')
  assert.notEqual(getDriverFinancialStatusLabel(row), 'در انتظار پرداخت')
})

test('zero balance with available credit stays fully paid and green', () => {
  const row = summary({
    overdue_debt: '0.00',
    driver_total_balance: '0.00',
    available_credit: '500.00',
  })
  assert.equal(getDriverFinancialStatus(row), 'paid')
  assert.equal(getDriverFinancialStatusLabel(row), 'تسویه‌شده')
  assert.match(DRIVER_FINANCIAL_STATUS_STYLES.paid.row, /emerald/)
})

test('zero balance without credit is fully paid and green', () => {
  const row = summary({
    overdue_debt: '0.00',
    driver_total_balance: '0.00',
    available_credit: '0.00',
  })
  assert.equal(getDriverFinancialStatus(row), 'paid')
  assert.equal(getDriverFinancialStatusLabel(row), 'تسویه‌شده')
  assert.match(DRIVER_FINANCIAL_STATUS_STYLES.paid.row, /emerald/)
})

test('invalid financial amounts produce an unknown neutral status', () => {
  for (const invalidAmount of [
    '',
    '   ',
    null,
    undefined,
    'not-a-number',
    'Infinity',
  ]) {
    assert.equal(parseMoney(invalidAmount), null)
    assert.equal(
      getDriverFinancialStatus({
        overdue_debt: invalidAmount,
        driver_total_balance: '0.00',
      }),
      'unknown',
    )
    assert.equal(
      getDriverFinancialStatus({
        overdue_debt: '0.00',
        driver_total_balance: invalidAmount,
      }),
      'unknown',
    )
  }

  assert.equal(
    getDriverFinancialStatus({ overdue_debt: '0.00' }),
    'unknown',
  )
  assert.equal(
    getDriverFinancialStatusLabel({
      overdue_debt: '0.00',
      driver_total_balance: 'not-a-number',
    }),
    'نامشخص',
  )
  assert.match(DRIVER_FINANCIAL_STATUS_STYLES.unknown.row, /slate/)
  assert.doesNotMatch(
    DRIVER_FINANCIAL_STATUS_STYLES.unknown.row,
    /emerald|green/,
  )
})

test('every status has a distinct row colour and legend label', () => {
  const rows = new Set(
    Object.values(DRIVER_FINANCIAL_STATUS_STYLES).map((style) => style.row),
  )
  const legends = new Set(
    Object.values(DRIVER_FINANCIAL_STATUS_STYLES).map((style) => style.legend),
  )
  assert.equal(rows.size, 4)
  assert.equal(legends.size, 4)
})
