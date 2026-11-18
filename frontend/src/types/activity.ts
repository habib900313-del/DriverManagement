export type ActivityModule =
  | 'drivers'
  | 'payments'
  | 'users'
  | 'documents'
  | 'auth'
  | 'other'

export type ActivityStatus = 'success' | 'failure'

export interface ActivityLogListItem {
  id: number
  timestamp: string
  actor_username: string
  action: string
  module: string
  description: string
  target_type: string
  target_id: string
  target_label: string
  status: ActivityStatus
  status_label: string
  ip_address: string | null
}

export interface ActivityLogDetail extends ActivityLogListItem {
  metadata: Record<string, unknown>
  before_data: Record<string, unknown> | null
  after_data: Record<string, unknown> | null
}

export interface ActivityLogModuleOption {
  value: string
  label: string
}

export interface ActivityLogFilterOptions {
  modules: ActivityLogModuleOption[]
  actions: string[]
  actors: string[]
}

export interface ActivityLogListParams {
  actor?: string
  action?: string
  module?: string
  status?: ActivityStatus | ''
  date_from?: string
  date_to?: string
  search?: string
  page?: number
  page_size?: number
}
