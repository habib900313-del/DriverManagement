import { useEffect } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Spinner } from './ui/Spinner'

interface ProtectedRouteProps {
  requiredRole?: 'manager' | 'superuser'
}

export function ProtectedRoute({ requiredRole }: ProtectedRouteProps) {
  const { user, loading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const { notify } = useToast()
  const hasRequiredRole =
    !requiredRole ||
    Boolean(
      requiredRole === 'superuser'
        ? user?.is_superuser
        : user?.is_staff || user?.is_superuser,
    )
  const accessDenied = !loading && Boolean(user) && !hasRequiredRole

  useEffect(() => {
    if (!accessDenied) return
    notify(
      'error',
      requiredRole === 'superuser'
        ? 'این صفحه فقط برای Superuser قابل دسترسی است.'
        : 'برای انجام این عملیات به نقش Admin یا Superuser نیاز دارید.',
    )
    navigate('/', { replace: true })
  }, [accessDenied, navigate, notify, requiredRole])

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-100 text-slate-500">
        <Spinner className="size-8" />
        <p className="text-sm">در حال بررسی نشست کاربر…</p>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (accessDenied) return null

  return <Outlet />
}
