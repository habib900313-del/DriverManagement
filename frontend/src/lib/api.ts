import type { CreateManagedUserInput, ManagedUser, User } from '../types/auth'
import type {
  AllocationConsumptionListItem,
  CashRevenueReport,
  ConservationReport,
  ConsumeCreditInput,
  CorrectAllocationInput,
  CorrectCreditInput,
  CorrectPaymentInput,
  DriverFinancialSummary,
  DriverFeeHistoryListItem,
  DriverPeriodsResponse,
  FeeScheduleInput,
  DriverPeriodCoverage,
  FeeScheduleListItem,
  FeeStartDateInput,
  FinancialReport,
  PaymentListItem,
  ReceivePaymentInput,
  ReverseAdjustmentInput,
  AdjustmentInput,
  AdjustmentListItem,
} from '../types/financial'
import type {
  Driver,
  DriverListParams,
  DriverPayload,
  DriverStats,
  FieldErrors,
  PaginatedResponse,
  UniqueCheckResult,
} from '../types/driver'

const API_BASE = '/api'

export interface HealthResponse {
  status: 'ok' | 'degraded'
  service: string
  version: string
  database: 'ok' | 'unavailable'
  timezone: string
  server_time: string
}

export async function fetchManagedUsers(signal?: AbortSignal): Promise<ManagedUser[]> {
  return request('/users/', { signal })
}

export async function createManagedUser(
  payload: CreateManagedUserInput,
): Promise<ManagedUser> {
  return request('/users/', { method: 'POST', body: payload })
}

export class ApiError extends Error {
  status: number
  payload: unknown
  fieldErrors: FieldErrors

  constructor(message: string, status: number, payload: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
    this.fieldErrors = collectFieldErrors(payload)
  }
}

function readCookie(name: string): string | null {
  const prefix = `${name}=`
  const parts = document.cookie ? document.cookie.split(';') : []
  for (const part of parts) {
    const value = part.trim()
    if (value.startsWith(prefix)) {
      return decodeURIComponent(value.slice(prefix.length))
    }
  }
  return null
}

function extractMessage(payload: unknown): string {
  if (!payload) return 'خطای نامشخصی رخ داد.'
  if (typeof payload === 'string') {
    const text = payload.trim()
    if (!text) return 'خطای نامشخصی رخ داد.'
    if (text.startsWith('<!DOCTYPE') || text.startsWith('<html')) {
      return 'خطای سرور رخ داد. لطفاً دوباره تلاش کنید.'
    }
    return text
  }
  if (Array.isArray(payload)) {
    const messages = payload.map((item) => extractMessage(item)).filter(Boolean)
    return messages.length ? messages.join(' ') : 'خطای نامشخصی رخ داد.'
  }
  if (typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    if (typeof record.detail === 'string') return record.detail
    if (typeof record.message === 'string') return record.message
    for (const value of Object.values(record)) {
      const message = extractMessage(value)
      if (message && message !== 'خطای نامشخصی رخ داد.') return message
    }
    if (Array.isArray(record.non_field_errors)) {
      return extractMessage(record.non_field_errors)
    }
  }
  return 'خطای نامشخصی رخ داد.'
}

function collectFieldErrors(payload: unknown): FieldErrors {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return {}
  }
  const result: FieldErrors = {}
  for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
    if (Array.isArray(value)) {
      result[key as keyof FieldErrors] = value.map((item) => String(item))
    } else if (typeof value === 'string') {
      result[key as keyof FieldErrors] = [value]
    }
  }
  return result
}

let csrfPromise: Promise<void> | null = null

export async function ensureCsrfCookie(): Promise<void> {
  if (readCookie('csrftoken')) return
  if (!csrfPromise) {
    csrfPromise = fetch(`${API_BASE}/auth/csrf/`, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
      .then(() => undefined)
      .finally(() => {
        csrfPromise = null
      })
  }
  return csrfPromise
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined

  if (method !== 'GET') {
    await ensureCsrfCookie()
    const token = readCookie('csrftoken')
    if (token) headers['X-CSRFToken'] = token
  }

  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers,
    body,
    signal: options.signal,
  })

  let payload: unknown = null
  if (response.status !== 204) {
    const contentType = response.headers.get('content-type') ?? ''
    if (contentType.includes('application/json')) {
      payload = await response.json()
    } else {
      payload = await response.text()
    }
  }

  if (!response.ok) {
    if (
      response.status === 401 &&
      !path.startsWith('/auth/login') &&
      !path.startsWith('/auth/me')
    ) {
      window.dispatchEvent(new CustomEvent('dm:unauthorized'))
    }
    throw new ApiError(extractMessage(payload), response.status, payload)
  }

  return payload as T
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health/', { signal })
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------
export async function login(username: string, password: string): Promise<User> {
  await ensureCsrfCookie()
  return request<User>('/auth/login/', {
    method: 'POST',
    body: { username, password },
  })
}

export async function logout(): Promise<void> {
  await request<{ detail: string }>('/auth/logout/', { method: 'POST' })
}

export async function fetchMe(signal?: AbortSignal): Promise<User | null> {
  try {
    return await request<User>('/auth/me/', { signal })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

// ---------------------------------------------------------------------------
// Drivers
// ---------------------------------------------------------------------------
function buildQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') {
      query.set(key, String(value))
    }
  }
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

export async function fetchDrivers(
  params: DriverListParams,
  signal?: AbortSignal,
): Promise<PaginatedResponse<Driver>> {
  const query = buildQuery({
    search: params.search,
    status: params.status,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  })
  return request<PaginatedResponse<Driver>>(`/drivers/${query}`, { signal })
}

export async function fetchDriver(id: number, signal?: AbortSignal): Promise<Driver> {
  return request<Driver>(`/drivers/${id}/`, { signal })
}

export async function fetchDriverStats(signal?: AbortSignal): Promise<DriverStats> {
  return request<DriverStats>('/drivers/stats/', { signal })
}

function buildDriverBody(payload: DriverPayload): FormData | Record<string, unknown> {
  const strOrEmpty = (v: string | null | undefined): string => v ?? ''
  if (payload.photo) {
    const form = new FormData()
    form.append('driver_code', strOrEmpty(payload.driver_code))
    form.append('full_name', strOrEmpty(payload.full_name))
    form.append('father_name', strOrEmpty(payload.father_name))
    form.append('phone', strOrEmpty(payload.phone))
    form.append('tazkira_number', strOrEmpty(payload.tazkira_number))
    form.append('plate_number', strOrEmpty(payload.plate_number))
    form.append('address', strOrEmpty(payload.address))
    form.append('registration_date', strOrEmpty(payload.registration_date))
    form.append('fee_start_date', strOrEmpty(payload.fee_start_date))
    form.append('status', String(payload.status))
    form.append('photo', payload.photo)
    return form
  }

  return {
    driver_code: strOrEmpty(payload.driver_code),
    full_name: strOrEmpty(payload.full_name),
    father_name: strOrEmpty(payload.father_name),
    phone: strOrEmpty(payload.phone),
    tazkira_number: strOrEmpty(payload.tazkira_number),
    plate_number: strOrEmpty(payload.plate_number),
    address: strOrEmpty(payload.address),
    registration_date: strOrEmpty(payload.registration_date),
    fee_start_date: strOrEmpty(payload.fee_start_date),
    status: payload.status,
  }
}

export async function createDriver(payload: DriverPayload): Promise<Driver> {
  return request<Driver>('/drivers/', {
    method: 'POST',
    body: buildDriverBody(payload),
  })
}

export async function updateDriver(
  id: number,
  payload: DriverPayload,
): Promise<Driver> {
  return request<Driver>(`/drivers/${id}/`, {
    method: 'PATCH',
    body: buildDriverBody(payload),
  })
}

export async function setDriverStatus(id: number, status: boolean): Promise<Driver> {
  return request<Driver>(`/drivers/${id}/status/`, {
    method: 'POST',
    body: { status },
  })
}

export async function checkDriverUnique(
  params: { driver_code?: string; plate_number?: string; exclude?: number },
  signal?: AbortSignal,
): Promise<UniqueCheckResult> {
  const query = buildQuery({
    driver_code: params.driver_code,
    plate_number: params.plate_number,
    exclude: params.exclude,
  })
  return request<UniqueCheckResult>(`/drivers/check-unique/${query}`, { signal })
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export interface DocumentUploadItem {
  id: number
  document_name: string
  original_filename: string
  file_size_mb: number
  upload_date: string
  status: string
}

export interface DocumentUploadResponse {
  driver_id: number
  documents: DocumentUploadItem[]
}

export async function uploadDocuments(
  driverId: number,
  files: FileList | File[],
): Promise<DocumentUploadResponse> {
  const form = new FormData()
  form.append("driver_id", String(driverId))
  const fileList = Array.isArray(files) ? files : Array.from(files)
  for (const file of fileList) {
    form.append("documents", file)
  }
  return request<DocumentUploadResponse>("/api/documents/upload/", {
    method: "POST",
    body: form,
  })
}

export async function fetchDriverDocuments(
  driverId: number,
  signal?: AbortSignal,
): Promise<DocumentUploadItem[]> {
  const query = new URLSearchParams({ driver_id: String(driverId) })
  return request<DocumentUploadItem[]>(`/api/documents/?${query}`, { signal })
}

export async function downloadDocument(
  documentId: number,
): Promise<Blob> {
  const response = await fetch(`${API_BASE}/documents/${documentId}/download/`, {
    method: "GET",
    credentials: "include",
    headers: {
      // No Accept header needed; we want the raw file
    },
  })
  if (!response.ok) {
    const payload = await response.text()
    throw new ApiError(extractMessage(payload), response.status, payload)
  }
  return response.blob()
}

export async function deactivateDocument(
  documentId: number,
): Promise<void> {
  return request(`/documents/${documentId}/deactivate/`, {
    method: "POST",
  })
}

// ---------------------------------------------------------------------------
// Financial (Payments)
// ---------------------------------------------------------------------------

export async function fetchFinancialSummary(
  driverId: number,
  asOf?: string,
  signal?: AbortSignal,
): Promise<DriverFinancialSummary> {
  const query = asOf ? `?as_of=${asOf}` : ''
  return request(`/drivers/${driverId}/financial-summary/${query}`, { signal })
}

export async function fetchDriverPeriods(
  driverId: number,
  signal?: AbortSignal,
  lookahead?: number,
): Promise<DriverPeriodsResponse> {
  const query = lookahead ? `?lookahead=${lookahead}` : ''
  return request(`/drivers/${driverId}/periods/${query}`, { signal })
}

export async function fetchDriverPeriodCoverage(
  driverId: number,
  asOf?: string,
  signal?: AbortSignal,
): Promise<DriverPeriodCoverage> {
  const query = asOf ? `?as_of=${asOf}` : ''
  return request(`/drivers/${driverId}/period-coverage/${query}`, { signal })
}

export async function fetchDriverConservation(
  driverId: number,
  asOf?: string,
  signal?: AbortSignal,
): Promise<ConservationReport> {
  const query = asOf ? `?as_of=${asOf}` : ''
  return request(`/drivers/${driverId}/conservation/${query}`, { signal })
}

export async function fetchDriverFeeHistory(
  driverId: number,
  signal?: AbortSignal,
): Promise<DriverFeeHistoryListItem[]> {
  return request(`/drivers/${driverId}/fee-history/`, { signal })
}

export async function fetchCashRevenueReport(
  asOf?: string,
  dateFrom?: string,
  dateTo?: string,
  signal?: AbortSignal,
): Promise<CashRevenueReport> {
  const query = new URLSearchParams()
  if (asOf) query.set('as_of', asOf)
  if (dateFrom) query.set('date_from', dateFrom)
  if (dateTo) query.set('date_to', dateTo)
  const encoded = query.toString()
  return request(`/reports/cash-revenue/${encoded ? `?${encoded}` : ''}`, { signal })
}

export async function fetchFinancialReport(
  asOf?: string,
  dateFrom?: string,
  dateTo?: string,
  signal?: AbortSignal,
): Promise<FinancialReport> {
  const query = new URLSearchParams()
  if (asOf) query.set('as_of', asOf)
  if (dateFrom) query.set('date_from', dateFrom)
  if (dateTo) query.set('date_to', dateTo)
  const encoded = query.toString()
  return request(`/reports/financial/${encoded ? `?${encoded}` : ''}`, { signal })
}

export async function receivePayment(payload: ReceivePaymentInput): Promise<PaymentListItem> {
  return request('/payments/', {
    method: 'POST',
    body: payload,
  })
}

export async function voidPayment(
  paymentId: number,
  reason: string,
): Promise<PaymentListItem> {
  return request(`/payments/${paymentId}/void/`, {
    method: 'POST',
    body: { reason },
  })
}

export async function correctPayment(
  paymentId: number,
  payload: CorrectPaymentInput,
): Promise<PaymentListItem> {
  return request(`/payments/${paymentId}/correct/`, {
    method: 'POST',
    body: payload,
  })
}

export async function correctAllocation(
  allocationId: number,
  payload: CorrectAllocationInput,
): Promise<unknown> {
  return request(`/allocations/${allocationId}/correct/`, {
    method: 'POST',
    body: payload,
  })
}

export async function correctCreditAllocation(
  allocationId: number,
  payload: CorrectCreditInput,
): Promise<unknown> {
  return request(`/allocations/${allocationId}/correct-credit/`, {
    method: 'POST',
    body: payload,
  })
}

export async function consumeCredit(
  payload: ConsumeCreditInput,
): Promise<AllocationConsumptionListItem> {
  return request('/credits/consume/', {
    method: 'POST',
    body: payload,
  })
}

export async function fetchAdjustments(
  driverId?: number,
  signal?: AbortSignal,
): Promise<AdjustmentListItem[]> {
  const query = driverId !== undefined ? `?driver_id=${driverId}` : ''
  return request(`/adjustments/${query}`, { signal })
}

export async function createAdjustment(
  payload: AdjustmentInput,
): Promise<AdjustmentListItem> {
  return request('/adjustments/', {
    method: 'POST',
    body: payload,
  })
}

export async function reverseAdjustment(
  adjustmentId: number,
  payload: ReverseAdjustmentInput,
): Promise<AdjustmentListItem> {
  return request(`/adjustments/${adjustmentId}/reverse/`, {
    method: 'POST',
    body: payload,
  })
}

export async function unsettleAndReverse(
  adjustmentId: number,
  payload: ReverseAdjustmentInput,
): Promise<AdjustmentListItem> {
  return request(`/adjustments/${adjustmentId}/unsettle-and-reverse/`, {
    method: 'POST',
    body: payload,
  })
}

export async function fetchFeeSchedule(
  signal?: AbortSignal,
): Promise<FeeScheduleListItem[]> {
  return request('/fee-schedule/', { signal })
}

export async function createFeeSchedule(
  payload: FeeScheduleInput,
): Promise<FeeScheduleListItem> {
  return request('/fee-schedule/', {
    method: 'POST',
    body: payload,
  })
}

export async function changeFeeStartDate(
  driverId: number,
  payload: FeeStartDateInput,
): Promise<DriverFeeHistoryListItem> {
  return request(`/drivers/${driverId}/fee-start-date/`, {
    method: 'POST',
    body: payload,
  })
}
