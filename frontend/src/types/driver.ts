export interface Driver {
  id: number
  driver_code: string
  full_name: string
  father_name: string | null
  phone: string | null
  tazkira_number: string | null
  plate_number: string
  address: string
  photo_url: string | null
  registration_date: string
  fee_start_date: string
  status: boolean
  status_label: string
  is_deleted: boolean
  deleted_at: string | null
  created_at: string
  updated_at: string
}

export interface DriverSummary {
  id: number
  driver_code: string
  full_name: string
  plate_number: string
  status: boolean
  status_label: string
  photo_url: string | null
  registration_date: string
}

export interface DriverStats {
  total: number
  active: number
  inactive: number
  recent: DriverSummary[]
}

export interface DriverPayload {
  driver_code: string
  full_name: string
  father_name: string
  phone: string
  tazkira_number: string
  plate_number: string
  address?: string | null
  registration_date: string
  fee_start_date: string
  status: boolean
  /** Only sent to the API; responses expose `photo_url` instead. */
  photo?: File | null
  /** PDF documents to upload with the driver */
  documents?: FileList | File[]
  initial_payment_amount?: string
  initial_payment_date?: string
  initial_payment_period_start?: string
  initial_payment_idempotency_key?: string
}

export interface DriverListParams {
  search?: string
  status?: 'active' | 'inactive' | ''
  ordering?: string
  serial_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type DriverField =
  | 'driver_code'
  | 'full_name'
  | 'father_name'
  | 'phone'
  | 'tazkira_number'
  | 'plate_number'
  | 'address'
  | 'registration_date'
  | 'fee_start_date'
  | 'status'
  | 'photo'

export type FieldErrors = Partial<Record<DriverField | 'non_field_errors', string[]>>

export interface UniqueCheckResult {
  driver_code_taken?: boolean
  plate_number_taken?: boolean
}
