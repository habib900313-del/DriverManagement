import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import {
  ApiError,
  downloadDocument,
  fetchDriverDocuments,
  uploadDocuments,
} from './api.ts'

const originalFetch = globalThis.fetch
const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')

function setBrowserGlobals() {
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: { cookie: 'csrftoken=test-token' },
  })
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      unauthorizedEvents: 0,
      dispatchEvent() {
        this.unauthorizedEvents += 1
      },
      location: { pathname: '/drivers/1' },
    },
  })
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  globalThis.fetch = originalFetch
  if (originalDocument) {
    Object.defineProperty(globalThis, 'document', originalDocument)
  } else {
    delete globalThis.document
  }
  if (originalWindow) {
    Object.defineProperty(globalThis, 'window', originalWindow)
  } else {
    delete globalThis.window
  }
})

test('document list supports empty results and missing optional fields', async () => {
  setBrowserGlobals()
  globalThis.fetch = async () =>
    jsonResponse({
      documents: [
        {
          id: 8,
          original_filename: 'license.pdf',
        },
      ],
    })

  const [document] = await fetchDriverDocuments(2)
  assert.equal(document.id, 8)
  assert.equal(document.document_name, 'license.pdf')
  assert.equal(document.content_type, 'application/pdf')
  assert.equal(document.file_size_mb, 0)
  assert.equal(document.description, '')
  assert.equal(document.upload_date, '')
  assert.equal(document.status, 'active')

  globalThis.fetch = async () => jsonResponse({ documents: [] })
  assert.deepEqual(await fetchDriverDocuments(2), [])
})

test('malformed document-list responses fail with a readable API error', async () => {
  setBrowserGlobals()
  globalThis.fetch = async () => jsonResponse({ unexpected: [] })

  await assert.rejects(fetchDriverDocuments(2), (error) => {
    assert.ok(error instanceof ApiError)
    assert.match(error.message, /فهرست اسناد/)
    return true
  })
})

test('network failure while refreshing documents is surfaced', async () => {
  setBrowserGlobals()
  globalThis.fetch = async () => {
    throw new TypeError('Failed to fetch')
  }

  await assert.rejects(fetchDriverDocuments(2), /Failed to fetch/)
})

test('successful repeated uploads use the upload endpoint', async () => {
  setBrowserGlobals()
  const requests = []
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options })
    return jsonResponse({ driver_id: 2, documents: [] }, 201)
  }
  const file = new File(['%PDF-1.4'], 'license.pdf', {
    type: 'application/pdf',
  })

  await uploadDocuments(2, [file])
  await uploadDocuments(2, [file])

  assert.equal(requests.length, 2)
  assert.equal(requests[0].url, '/api/documents/upload/')
  assert.equal(requests[0].options.method, 'POST')
  assert.equal(requests[0].options.body.getAll('documents').length, 1)
})

test('a successful upload is present after the document-list refresh', async () => {
  setBrowserGlobals()
  const uploadedItem = {
    id: 21,
    document_name: 'identity.png',
    original_filename: 'identity.png',
    content_type: 'image/png',
    file_size_mb: 0.02,
    upload_date: '2026-11-15T09:00:00Z',
    description: '',
    status: 'active',
  }
  globalThis.fetch = async (url, options) => {
    if (options.method === 'POST') {
      return jsonResponse({ driver_id: 2, documents: [uploadedItem] }, 201)
    }
    return jsonResponse({ documents: [uploadedItem] })
  }

  const image = new File(['image'], 'identity.png', { type: 'image/png' })
  await uploadDocuments(2, [image])
  const documents = await fetchDriverDocuments(2)

  assert.equal(documents.length, 1)
  assert.equal(documents[0].id, uploadedItem.id)
  assert.equal(documents[0].content_type, 'image/png')
})

test('failed uploads are surfaced instead of reported as successful', async () => {
  setBrowserGlobals()
  globalThis.fetch = async () =>
    jsonResponse({ detail: 'آپلود رد شد.' }, 400)

  await assert.rejects(uploadDocuments(2, []), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 400)
    assert.equal(error.message, 'آپلود رد شد.')
    return true
  })
})

test('failed downloads surface API errors and expired authentication', async () => {
  setBrowserGlobals()
  globalThis.fetch = async () =>
    jsonResponse({ detail: 'نشست ورود منقضی شده است.' }, 401)

  await assert.rejects(downloadDocument(8), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 401)
    return true
  })
  assert.equal(globalThis.window.unauthorizedEvents, 1)
})

test('successful downloads return a blob', async () => {
  setBrowserGlobals()
  globalThis.fetch = async () =>
    new Response(new Uint8Array([37, 80, 68, 70]), {
      status: 200,
      headers: { 'Content-Type': 'application/pdf' },
    })

  const blob = await downloadDocument(8)
  assert.equal(blob.type, 'application/pdf')
  assert.equal(blob.size, 4)
})
