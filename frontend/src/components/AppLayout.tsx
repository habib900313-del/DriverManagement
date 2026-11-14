import { useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { cn } from '../lib/cn'
import { getErrorMessage } from '../lib/errors'
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

const navItems = [
  { to: '/', label: 'داشبورد', icon: DashboardIcon },
  { to: '/drivers', label: 'رانندگان', icon: UsersIcon },
  { to: '/drivers/new', label: 'ثبت راننده جدید', icon: PlusIcon },
  { to: '/financial', label: 'داشبورد مالی', icon: DashboardIcon },
  { to: '/financial/payments/new', label: 'ثبت پرداخت', icon: CreditCardIcon },
  { to: '/financial/history', label: 'سوابق پرداخت', icon: HistoryIcon },
  { to: '/financial/reports/cash-revenue', label: 'گزارش درآمد نقدی', icon: DashboardIcon },
  { to: '/financial/reports/financial', label: 'گزارش مالی جامع', icon: DashboardIcon },
]

function pageTitle(pathname: string): string {
  if (pathname === '/') return 'داشبورد'
  if (pathname === '/drivers') return 'فهرست رانندگان'
  if (pathname === '/drivers/new') return 'ثبت راننده جدید'
  if (/^\/drivers\/\d+\/edit$/.test(pathname)) return 'ویرایش راننده'
  if (/^\/drivers\/\d+$/.test(pathname)) return 'پروفایل راننده'
  if (pathname === '/financial') return 'داشبورد مالی'
  if (pathname === '/financial/payments/new') return 'ثبت پرداخت'
  if (pathname === '/financial/history') return 'سوابق پرداخت'
  if (pathname === '/users') return 'مدیریت کاربران'
  if (pathname === '/financial/reports/cash-revenue') return 'گزارش درآمد نقدی'
  if (/^\/financial\/drivers\/\d+$/.test(pathname)) return 'پروفایل مالی راننده'
  return 'سیستم مدیریت رانندگان'
}

export function AppLayout() {
  const { user, logout } = useAuth()
  const { notify } = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)

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

  const sidebar = (
    <div className="flex h-full flex-col bg-slate-900 text-slate-200">
      <div className="flex h-16 items-center justify-between border-b border-white/10 px-5">
        <Link
          to="/"
          onClick={() => setSidebarOpen(false)}
          className="flex items-center gap-2.5"
        >
          <span className="flex size-9 items-center justify-center rounded-xl bg-white/10 text-white ring-1 ring-white/15">
            <ShieldIcon className="size-5" />
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-bold text-white">
              مدیریت رانندگان
            </span>
            <span className="block text-[11px] text-slate-400">
              سیستم اداری محلی
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

      <nav className="flex-1 space-y-1 px-3 py-4">
        <p className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-slate-500">
          بخش‌های اصلی
        </p>
        {navItems.map((item) => {
          const Icon = item.icon
          const active = isActive(item.to)
          return (
            <Link
              key={item.to}
              to={item.to}
              onClick={() => setSidebarOpen(false)}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition',
                active
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-300 hover:bg-white/10 hover:text-white',
              )}
            >
              <Icon
                className={cn(
                  'size-5',
                  active ? 'text-slate-900' : 'text-slate-400',
                )}
              />
              {item.label}
            </Link>
          )
        })}
        {user?.is_superuser && (
          <Link
            to="/users"
            onClick={() => setSidebarOpen(false)}
            aria-current={location.pathname === '/users' ? 'page' : undefined}
            className={cn(
              'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition',
              location.pathname === '/users'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-300 hover:bg-white/10 hover:text-white',
            )}
          >
            <UserIcon className="size-5 text-slate-400" />
            مدیریت کاربران
          </Link>
        )}
      </nav>

      <div className="border-t border-white/10 p-3">
        <div className="flex items-center gap-3 rounded-xl bg-white/5 px-3 py-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-white/10 text-sm font-semibold text-white">
            {(user?.display_name || user?.username || 'م').charAt(0)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">
              {user?.display_name || user?.username}
            </p>
            <p className="text-[11px] text-slate-400">مدیر سیستم</p>
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
          نسخه ۰.۱.۰ — داده‌ها روی همین دستگاه
        </p>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-slate-100">
      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-slate-900/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="بستن پوشش منو"
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 start-0 z-40 w-64 shadow-2xl transition-transform duration-200 lg:translate-x-0 lg:shadow-none',
          sidebarOpen ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        {sidebar}
      </aside>

      <div className="flex min-h-screen flex-col lg:ps-64">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
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
                سیستم مدیریت رانندگان — اداره محلی
              </p>
            </div>
            <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-slate-50 py-1 pe-1 ps-3 text-xs text-slate-600 sm:flex">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              <span>متصل به سیستم محلی</span>
              <span className="flex size-7 items-center justify-center rounded-full bg-white font-semibold text-slate-700 shadow-sm">
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
