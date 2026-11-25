import assert from 'node:assert/strict'
import { test } from 'node:test'
import { deriveFirstFeePeriod } from './firstFeePeriod.ts'
import { jalaliQuarterEnd } from './dates.ts'

test('the first period starts exactly on the driver fee start date', () => {
  const period = deriveFirstFeePeriod('2026-11-09')
  assert.ok(period)
  assert.equal(period.start, '2026-11-09')
  assert.equal(period.end, jalaliQuarterEnd('2026-11-09'))
})

test('the first period never silently uses a different start date', () => {
  for (const date of ['2026-01-01', '2026-04-01', '2026-11-09', '2027-02-07']) {
    assert.equal(deriveFirstFeePeriod(date)?.start, date)
  }
})

test('the first period keeps the three-month duration', () => {
  const period = deriveFirstFeePeriod('2026-11-09')
  assert.ok(period)
  assert.notEqual(period.start, period.end)
  assert.equal(period.end, '2027-02-06')
})

test('a missing or malformed fee start date yields no period', () => {
  assert.equal(deriveFirstFeePeriod(''), null)
  assert.equal(deriveFirstFeePeriod('01/04/2026'), null)
  assert.equal(deriveFirstFeePeriod('2026-02-30'), null)
})

test('dates outside the supported range yield no period', () => {
  assert.equal(deriveFirstFeePeriod('1899-12-31'), null)
  assert.equal(deriveFirstFeePeriod('2101-01-01'), null)
})
