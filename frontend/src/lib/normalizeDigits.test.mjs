import assert from 'node:assert/strict'
import { test } from 'node:test'
import { normalizeDigits } from './digits.ts'

test('normalizes Persian digits to English digits', () => {
  assert.equal(normalizeDigits('۰۱۲۳۴۵۶۷۸۹'), '0123456789')
})

test('normalizes Arabic digits to English digits', () => {
  assert.equal(normalizeDigits('٠١٢٣٤٥٦٧٨٩'), '0123456789')
})

test('keeps English digits unchanged', () => {
  assert.equal(normalizeDigits('0123456789'), '0123456789')
})

test('normalizes mixed Persian, Arabic and English digits', () => {
  assert.equal(normalizeDigits('۱2٣4۵6٧8۹'), '123456789')
})

test('leaves non-digit characters untouched so validation can reject them', () => {
  assert.equal(normalizeDigits('۱۲-abc'), '12-abc')
})

test('empty input stays empty', () => {
  assert.equal(normalizeDigits(''), '')
})
