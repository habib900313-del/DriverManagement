import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { cn } from '../lib/cn'
import { getErrorMessage } from '../lib/errors'
import { fetchHealth } from '../lib/api'
import {
  DashboardIcon,
  LogOutIcon,
  PlusIcon,
  ShieldIcon,
  UsersIcon,
  XIcon,
  CreditCardIcon,
  HistoryIcon,
  UserIcon,
} from './icons'
import { Spinner } from './ui/Spinner'

type ServerStatus = 'checking' | 'online' | 'degraded' | 'offline'

const navItems = [
  { to: '/', label: 'داشبورد', icon: DashboardIcon, managerOnly: false },
  { to: '/drivers', label: 'رانندگان', icon: UsersIcon, managerOnly: false },
  { to: '/drivers/archived', label: 'رانندگان آرشیف‌شده', icon: UsersIcon, managerOnly: true },
  { to: '/drivers/new', label: 'ثبت راننده جدید', icon: PlusIcon, managerOnly: true },
  { to: '/financial', label: 'داشبورد مالی', icon: DashboardIcon, managerOnly: false },
  { to: '/financial/payments/new', label: 'ثبت پرداخت', icon: CreditCardIcon, managerOnly: true },
  { to: '/financial/history', label: 'سوابق پرداخت', icon: HistoryIcon, managerOnly: false },
  { to: '/financial/reports/cash-revenue', label: 'گزارش درآمد نقدی', icon: DashboardIcon, managerOnly: false },
  { to: '/financial/reports/financial', label: 'گزارش مالی جامع', icon: DashboardIcon, managerOnly: false },
]

function pageTitle(pathname: string): string {
  if (pathname === '/') return 'داشبورد'
  if (pathname === '/drivers') return 'فهرست رانندگان'
  if (pathname === '/drivers/archived') return 'رانندگان آرشیف‌شده'
  if (pathname === '/drivers/new') return 'ثبت راننده جدید'
  if (/^\/drivers\/\d+\/edit$/.test(pathname)) return 'ویرایش راننده'
  if (/^\/drivers\/\d+$/.test(pathname)) return 'پروفایل راننده'
  if (pathname === '/financial') return 'داشبورد مالی'
  if (pathname === '/financial/payments/new') return 'ثبت پرداخت'
  if (pathname === '/financial/history') return 'سوابق پرداخت'
  if (pathname === '/users') return 'مدیریت کاربران'
  if (pathname === '/admin/activity-logs') return 'گزارش فعالیت کاربران'
  if (pathname === '/financial/reports/cash-revenue') return 'گزارش درآمد نقدی'
  if (/^\/financial\/drivers\/\d+$/.test(pathname)) return 'پروفایل مالی راننده'
  return 'سیستم مدیریت رانندگان'
}

export function AppLayout() {
  const { user, logout } = useAuth()
  const { notify } = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const canManage = Boolean(user?.is_staff || user?.is_superuser)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const [serverStatus, setServerStatus] = useState<ServerStatus>('checking')

  useEffect(() => {
    let active = true
    let refreshTimer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | null = null

    const checkServer = async () => {
      controller = new AbortController()
      try {
        const health = await fetchHealth(controller.signal)
        if (active) {
          setServerStatus(
            health.status === 'ok' && health.database === 'ok'
              ? 'online'
              : 'degraded',
          )
        }
      } catch {
        if (active) setServerStatus('offline')
      } finally {
        if (active) {
          refreshTimer = setTimeout(() => void checkServer(), 30_000)
        }
      }
    }

    void checkServer()
    return () => {
      active = false
      controller?.abort()
      if (refreshTimer) clearTimeout(refreshTimer)
    }
  }, [])

  const serverStatusLabel = {
    checking: 'در حال بررسی اتصال',
    online: 'متصل به سرور',
    degraded: 'سرور در دسترس است؛ پایگاه داده دچار اختلال است',
    offline: 'ارتباط با سرور قطع است',
  }[serverStatus]
  const compactServerStatusLabel = {
    checking: 'در حال بررسی',
    online: 'متصل به سرور',
    degraded: 'اختلال پایگاه داده',
    offline: 'ارتباط قطع است',
  }[serverStatus]
  const serverStatusDotClass =
    serverStatus === 'online'
      ? 'bg-emerald-500'
      : serverStatus === 'offline'
        ? 'bg-rose-500'
        : 'bg-amber-500'

  const isActive = (to: string) => {
    if (to === '/') return location.pathname === '/'
    if (to === '/drivers') {
      return (
        location.pathname === '/drivers' ||
        /^\/drivers\/\d+/.test(location.pathname)
      )
    }
    if (to.startsWith('/financial')) {
      return location.pathname.startsWith(to)
    }
    return location.pathname === to
  }

  const handleLogout = async () => {
    setLoggingOut(true)
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (error) {
      notify('error', getErrorMessage(error))
      navigate('/login', { replace: true })
    } finally {
      setLoggingOut(false)
    }
  }

  const navLinkClass = (active: boolean) =>
    cn(
      'group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-150',
      active
        ? 'bg-gradient-to-l from-brand-500 to-brand-600 text-white shadow-lg shadow-brand-950/40'
        : 'text-slate-300 hover:bg-white/5 hover:text-white',
    )

  const sidebar = (
    <div className="relative flex h-full flex-col bg-gradient-to-b from-slate-900 via-slate-900 to-brand-950 text-slate-200">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(28rem_14rem_at_50%_-20%,rgb(99_102_241_/_0.35),transparent_70%)]"
      />
      <div className="relative flex h-16 items-center justify-between border-b border-white/10 px-5">
        <Link
          to="/"
          onClick={() => setSidebarOpen(false)}
          className="flex items-center gap-2.5"
        >
          <span className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 text-white shadow-lg shadow-brand-900/50 ring-1 ring-white/20">
            <ShieldIcon className="size-5" />
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-bold text-white">
            سیستم مدیریت رانندگان
            </span>
            <span className="block text-[11px] text-slate-400">
            سامانه آنلاین مدیریت رانندگان
            </span>
          </span>
        </Link>
        <button
          type="button"
          onClick={() => setSidebarOpen(false)}
          className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white lg:hidden"
          aria-label="بستن منو"
        >
          <XIcon className="size-5" />
        </button>
      </div>

      <nav className="relative flex-1 space-y-1 overflow-y-auto px-3 py-4">
        <p className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-slate-500">
          بخش‌های اصلی
        </p>
        {navItems
          .filter((item) => !item.managerOnly || canManage)
          .map((item) => {
            const Icon = item.icon
            const active = isActive(item.to)
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setSidebarOpen(false)}
                aria-current={active ? 'page' : undefined}
                className={navLinkClass(active)}
              >
                {active && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-y-2 start-0 w-1 rounded-full bg-white/90"
                  />
                )}
                <Icon
                  className={cn(
                    'size-5 transition-colors',
                    active
                      ? 'text-white'
                      : 'text-slate-400 group-hover:text-brand-200',
                  )}
                />
                {item.label}
              </Link>
            )
          })}
        {user?.is_superuser && (
          <>
            <Link
              to="/users"
              onClick={() => setSidebarOpen(false)}
              aria-current={location.pathname === '/users' ? 'page' : undefined}
              className={navLinkClass(location.pathname === '/users')}
            >
              {location.pathname === '/users' && (
                <span
                  aria-hidden="true"
                  className="absolute inset-y-2 start-0 w-1 rounded-full bg-white/90"
                />
              )}
              <UserIcon
                className={cn(
                  'size-5 transition-colors',
                  location.pathname === '/users'
                    ? 'text-white'
                    : 'text-slate-400 group-hover:text-brand-200',
                )}
              />
              مدیریت کاربران
            </Link>
            <Link
              to="/admin/activity-logs"
              onClick={() => setSidebarOpen(false)}
              aria-current={
                location.pathname === '/admin/activity-logs' ? 'page' : undefined
              }
              className={navLinkClass(
                location.pathname === '/admin/activity-logs',
              )}
            >
              {location.pathname === '/admin/activity-logs' && (
                <span
                  aria-hidden="true"
                  className="absolute inset-y-2 start-0 w-1 rounded-full bg-white/90"
                />
              )}
              <HistoryIcon
                className={cn(
                  'size-5 transition-colors',
                  location.pathname === '/admin/activity-logs'
                    ? 'text-white'
                    : 'text-slate-400 group-hover:text-brand-200',
                )}
              />
              گزارش فعالیت کاربران
            </Link>
          </>
        )}
      </nav>

      <div className="relative border-t border-white/10 p-3">
        <div className="flex items-center gap-3 rounded-xl bg-white/5 px-3 py-2.5 ring-1 ring-white/5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-sm font-semibold text-white ring-1 ring-white/20">
            {(user?.display_name || user?.username || 'م').charAt(0)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">
              {user?.display_name || user?.username}
            </p>
            <p className="text-[11px] text-slate-400">
              {user?.is_superuser
                ? 'مدیر ارشد'
                : user?.is_staff
                  ? 'مدیر'
                  : 'کاربر'}
            </p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            disabled={loggingOut}
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-rose-300 disabled:opacity-50"
            aria-label="خروج از سیستم"
            title="خروج از سیستم"
          >
            {loggingOut ? <Spinner className="size-4" /> : <LogOutIcon className="size-4" />}
          </button>
        </div>
        <p className="px-1 pt-2 text-[10px] text-slate-500">
          نسخه ۰.۱.۰ — سامانه آنلاین مدیریت رانندگان
        </p>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen">
      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-slate-900/50 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="بستن پوشش منو"
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 start-0 z-40 w-64 shadow-2xl transition-transform duration-200 ease-out lg:translate-x-0 lg:shadow-none',
          sidebarOpen ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        {sidebar}
      </aside>

      <div className="flex min-h-screen flex-col lg:ps-64">
        <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/80 shadow-xs backdrop-blur-md">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="rounded-lg p-2 text-slate-600 transition hover:bg-slate-100 lg:hidden"
              aria-label="باز کردن منو"
            >
              <span className="flex flex-col gap-1">
                <span className="block h-0.5 w-5 rounded bg-current" />
                <span className="block h-0.5 w-5 rounded bg-current" />
                <span className="block h-0.5 w-5 rounded bg-current" />
              </span>
            </button>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-slate-800">
                {pageTitle(location.pathname)}
              </p>
              <p className="hidden text-[11px] text-slate-400 sm:block">
                سامانه آنلاین مدیریت رانندگان
              </p>
            </div>
            <div
              role="status"
              aria-live="polite"
              aria-label={serverStatusLabel}
              title={serverStatusLabel}
              className="flex min-w-0 max-w-[42vw] shrink-0 items-center gap-2 rounded-full border border-slate-200 bg-white/70 py-1 pe-1 ps-2 text-xs text-slate-600 shadow-xs sm:max-w-none sm:ps-3"
            >
              <span
                className={cn('size-1.5 shrink-0 rounded-full', serverStatusDotClass)}
              />
              <span className="truncate text-[10px] sm:hidden">
                {compactServerStatusLabel}
              </span>
              <span className="hidden sm:inline">
                {serverStatusLabel}
              </span>
              <span className="flex size-7 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-600 font-semibold text-white shadow-sm">
                {(user?.display_name || user?.username || 'م').charAt(0)}
              </span>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
