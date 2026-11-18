import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  addJalaliMonths,
  isoToJalali,
  jalaliQuarterEnd,
  jalaliToIso,
  isValidJalaliQuarterPeriod,
  validateDateRange,
} from './dates.ts'

const quarterCases = [
  {
    name: '30-day month',
    jalali: [1404, 7, 30],
    start: '2025-10-22',
    nextStart: '2026-01-20',
    end: '2026-01-19',
  },
  {
    name: '31st day clamped into a 30-day month',
    jalali: [1404, 6, 31],
    start: '2025-09-22',
    nextStart: '2025-12-21',
    end: '2025-12-20',
  },
  {
    name: '30th day clamped into non-leap Esfand',
    jalali: [1404, 9, 30],
    start: '2025-12-21',
    nextStart: '2026-03-20',
    end: '2026-03-19',
  },
  {
    name: '29-day Esfand',
    jalali: [1404, 12, 29],
    start: '2026-03-20',
    nextStart: '2026-06-19',
    end: '2026-06-18',
  },
  {
    name: '30 Esfand in a leap year',
    jalali: [1403, 12, 30],
    start: '2025-03-20',
    nextStart: '2025-06-20',
    end: '2025-06-19',
  },
]

for (const quarter of quarterCases) {
  test(`Jalali quarter calculation: ${quarter.name}`, () => {
    const [jy, jm, jd] = quarter.jalali
    assert.equal(jalaliToIso(jy, jm, jd), quarter.start)
    assert.deepEqual(isoToJalali(quarter.start), { jy, jm, jd })
    assert.equal(addJalaliMonths(quarter.start, 3), quarter.nextStart)
    assert.equal(jalaliQuarterEnd(quarter.start), quarter.end)
    assert.equal(
      isValidJalaliQuarterPeriod(quarter.start, quarter.start, quarter.end),
      true,
    )
  })
}

test('24 Aqrab maps to the day before 24 Dalw begins next quarter', () => {
  const start = jalaliToIso(1404, 8, 24)
  assert.equal(start, '2025-11-15')
  assert.equal(addJalaliMonths(start, 3), '2026-02-13')
  assert.equal(jalaliQuarterEnd(start), '2026-02-12')
})

test('date range validation accepts empty and ordered bounds', () => {
  assert.equal(validateDateRange('', ''), null)
  assert.equal(validateDateRange('2025-11-01', ''), null)
  assert.equal(validateDateRange('', '2025-11-30'), null)
  assert.equal(
    validateDateRange('2025-11-01', '2025-11-30', '2025-11-30'),
    null,
  )
})

test('date range validation rejects a start after the end', () => {
  assert.match(
    validateDateRange('2025-11-30', '2025-11-01') ?? '',
    /شروع نباید بعد از/,
  )
})

test('date range validation rejects an end after the report date', () => {
  assert.match(
    validateDateRange('2025-11-01', '2025-12-01', '2025-11-30') ?? '',
    /پایان نباید بعد از تاریخ محاسبه/,
  )
})
