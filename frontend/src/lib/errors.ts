import { ApiError } from './api'

export { normalizeDigits } from './digits'

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'خطای نامشخصی رخ داد. دوباره تلاش کنید.'
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
