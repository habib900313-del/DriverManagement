import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  isFeeStartDateChanged,
  validateFeeStartDateChange,
} from './driverFeeStartDate.ts'

const CURRENT = '2026-01-01'

test('an unchanged date needs no validation and no reason', () => {
  assert.equal(isFeeStartDateChanged(CURRENT, CURRENT), false)
  assert.deepEqual(validateFeeStartDateChange(CURRENT, CURRENT, ''), {})
})

test('a valid changed date with a reason passes validation', () => {
  assert.equal(isFeeStartDateChanged(CURRENT, '2026-04-01'), true)
  assert.deepEqual(
    validateFeeStartDateChange(CURRENT, '2026-04-01', 'اصلاح شروع فیس'),
    {},
  )
})

test('an invalid calendar date is rejected', () => {
  const errors = validateFeeStartDateChange(CURRENT, '2026-02-30', 'دلیل')
  assert.match(errors.date ?? '', /تاریخ معتبر/)
})

test('a malformed or empty date is rejected', () => {
  assert.ok(validateFeeStartDateChange(CURRENT, '', 'دلیل').date)
  assert.ok(validateFeeStartDateChange(CURRENT, '01/04/2026', 'دلیل').date)
})

test('dates outside the supported range are rejected', () => {
  assert.ok(validateFeeStartDateChange(CURRENT, '1899-12-31', 'دلیل').date)
  assert.ok(validateFeeStartDateChange(CURRENT, '2101-01-01', 'دلیل').date)
  assert.deepEqual(
    validateFeeStartDateChange(CURRENT, '2100-12-31', 'دلیل'),
    {},
  )
})

test('a changed date requires a non-blank reason', () => {
  assert.ok(validateFeeStartDateChange(CURRENT, '2026-04-01', '   ').reason)
  assert.ok(validateFeeStartDateChange(CURRENT, '2026-04-01', '').reason)
})

test('invalid date and missing reason are reported together', () => {
  const errors = validateFeeStartDateChange(CURRENT, 'bad-date', '   ')
  assert.ok(errors.date)
  assert.ok(errors.reason)
})

test('surrounding whitespace does not count as a date change', () => {
  assert.equal(isFeeStartDateChanged(CURRENT, `  ${CURRENT}  `), false)
})
