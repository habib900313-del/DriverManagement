export interface User {
  id: number
  username: string
  first_name: string
  last_name: string
  display_name: string
  is_staff: boolean
  is_superuser: boolean
}

export interface ManagedUser {
  id: number
  username: string
  full_name: string
  role: 'superuser' | 'admin' | 'guest'
  is_active: boolean
}

export interface CreateManagedUserInput {
  username: string
  full_name: string
  password: string
  password_confirmation: string
  role: 'admin' | 'guest'
}
