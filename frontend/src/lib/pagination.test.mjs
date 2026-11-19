import assert from 'node:assert/strict'
import { test } from 'node:test'
import { applyListChange, pageAfterDeletion } from './pagination.ts'

const base = {
  page: 3,
  page_size: 25,
  search: 'abc',
  date_from: '2026-01-01',
}

test('changing the page updates the current page', () => {
  assert.deepEqual(applyListChange(base, { page: 4 }), { ...base, page: 4 })
})

test('page navigation keeps the active filters', () => {
  const result = applyListChange(base, { page: 2 })
  assert.equal(result.page, 2)
  assert.equal(result.search, 'abc')
  assert.equal(result.date_from, '2026-01-01')
  assert.equal(result.page_size, 25)
})

test('page numbers are clamped to at least one', () => {
  assert.equal(applyListChange(base, { page: 0 }).page, 1)
  assert.equal(applyListChange(base, { page: -2 }).page, 1)
})

test('changing a filter resets to page 1', () => {
  assert.equal(applyListChange(base, { search: 'xyz' }).page, 1)
  assert.equal(applyListChange(base, { date_from: '2026-02-01' }).page, 1)
  assert.equal(applyListChange(base, { date_to: '2026-03-01' }).page, 1)
  assert.equal(applyListChange(base, { driver_id: 7 }).page, 1)
})

test('clearing a filter resets to page 1', () => {
  const result = applyListChange(base, { search: undefined })
  assert.equal(result.page, 1)
  assert.equal(result.search, undefined)
})

test('changing the page size resets to page 1', () => {
  assert.equal(applyListChange(base, { page_size: 50 }).page, 1)
})

test('deleting the last item on a page steps back one page', () => {
  assert.equal(pageAfterDeletion(3, 1), 2)
  assert.equal(pageAfterDeletion(2, 0), 1)
})

test('deleting the last item on the first page stays on page 1', () => {
  assert.equal(pageAfterDeletion(1, 1), 1)
})

test('deleting an item while others remain keeps the current page', () => {
  assert.equal(pageAfterDeletion(3, 2), 3)
})

test('deletion fallback moves back a page and keeps the filters', () => {
  const current = { ...base, page: 3 }
  const nextPage = pageAfterDeletion(current.page, 1)
  const result = applyListChange(current, { page: nextPage })
  assert.equal(result.page, 2)
  assert.equal(result.search, 'abc')
  assert.equal(result.date_from, '2026-01-01')
})
