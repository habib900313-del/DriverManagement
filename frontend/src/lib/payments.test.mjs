import assert from 'node:assert/strict'
import { test } from 'node:test'
import { getPaymentCorrectionDisabledReason } from './payments.ts'

test('received payments without refunds are eligible for correction', () => {
  assert.equal(
    getPaymentCorrectionDisabledReason({ status: 'received', refunds: [] }),
    null,
  )
})

test('payments with refunds or invalid status explain why correction is disabled', () => {
  assert.match(
    getPaymentCorrectionDisabledReason({
      status: 'received',
      refunds: [{ id: 1 }],
    }) ?? '',
    /برگشت پول/,
  )
  assert.match(
    getPaymentCorrectionDisabledReason({ status: 'corrected', refunds: [] }) ??
      '',
    /اصلاح‌شده/,
  )
})

test('missing refund history fails closed', () => {
  assert.match(
    getPaymentCorrectionDisabledReason({ status: 'received' }) ?? '',
    /قابل بررسی نیست/,
  )
})
