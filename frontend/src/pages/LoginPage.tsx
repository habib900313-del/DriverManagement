import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ensureCsrfCookie } from '../lib/api'
import { getErrorMessage } from '../lib/errors'
import {
  AlertCircleIcon,
  CheckIcon,
  EyeIcon,
  EyeOffIcon,
  LockIcon,
  ShieldIcon,
  UserIcon,
} from '../components/icons'
import { Spinner } from '../components/ui/Spinner'

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Prime the CSRF cookie before the first login attempt.
    void ensureCsrfCookie().catch(() => undefined)
  }, [])

  if (!loading && user) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submitting) return

    if (!username.trim() || !password) {
      setError('نام کاربری و رمز عبور را وارد کنید.')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await login(username.trim(), password)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from && from !== '/login' ? from : '/', { replace: true })
    } catch (cause) {
      setError(getErrorMessage(cause))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="size-8 text-brand-500" />
      </div>
    )
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-slate-900 via-slate-900 to-brand-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden="true"
          className="absolute inset-0 opacity-[0.15] [background-image:linear-gradient(to_right,rgb(255_255_255_/_0.25)_1px,transparent_1px),linear-gradient(to_bottom,rgb(255_255_255_/_0.25)_1px,transparent_1px)] [background-size:44px_44px]"
        />
        <div className="absolute -left-24 -top-24 size-72 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="absolute -bottom-32 -right-16 size-96 rounded-full bg-sky-500/15 blur-3xl" />
        <div className="relative">
          <div className="flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-400 to-brand-600 shadow-lg shadow-brand-900/50 ring-1 ring-white/20">
              <ShieldIcon className="size-6" />
            </span>
            <div>
              <p className="text-base font-bold">سیستم مدیریت رانندگان</p>
              <p className="text-xs text-slate-400">سامانه آنلاین مدیریت رانندگان</p>
            </div>
          </div>

          <h1 className="mt-16 max-w-md text-3xl font-bold leading-snug">
            مدیریت منظم رانندگان، از ثبت تا پیگیری وضعیت
          </h1>
          <p className="mt-4 max-w-md text-sm leading-7 text-slate-300">
            ثبت مشخصات، مدیریت اسناد، پیگیری پرداخت‌ها و نظارت بر وضعیت رانندگان
            در یک سامانه یکپارچه.
          </p>

          <ul className="mt-10 space-y-3 text-sm text-slate-300">
            {[
              'اطلاعات متمرکز روی سرور',
              'دسترسی محدود بر اساس سطح مجوز کاربران',
              'پشتیبانی از تقویم شمسی و میلادی',
              'دسترسی آنلاین برای کاربران دارای حساب مجاز',
            ].map((item) => (
              <li key={item} className="flex items-center gap-2.5">
                <span className="flex size-5 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
                  <CheckIcon className="size-3" />
                </span>
                {item}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-slate-500">
          اطلاعات شخصی و مالی رانندگان محرمانه است؛ دسترسی غیرمجاز ممنوع می‌باشد.
        </p>
      </div>

      <div className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <span className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-md shadow-brand-600/25">
              <ShieldIcon className="size-5" />
            </span>
            <div>
              <p className="text-sm font-bold text-slate-900">
                سیستم مدیریت رانندگان
              </p>
              <p className="text-xs text-slate-500">سامانه آنلاین مدیریت رانندگان</p>
            </div>
          </div>

          <div className="animate-fade-in-up rounded-2xl border border-slate-200 bg-white/95 p-6 shadow-xl shadow-brand-900/5 backdrop-blur sm:p-8">
            <div>
              <h2 className="text-xl font-bold text-slate-900">ورود مدیر سیستم</h2>
              <p className="mt-1 text-sm leading-6 text-slate-500">
                برای دسترسی به اطلاعات رانندگان، نام کاربری و رمز عبور خود را
                وارد کنید.
              </p>
            </div>

            {error && (
              <div
                className="mt-5 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700"
                role="alert"
              >
                <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <div className="space-y-1.5">
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-slate-700"
                >
                  نام کاربری
                </label>
                <div className="relative">
                  <UserIcon className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                  <input
                    id="username"
                    name="username"
                    autoComplete="username"
                    dir="ltr"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    className="h-11 w-full rounded-xl border border-slate-300 bg-white pe-3 ps-10 text-sm text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                    placeholder="نام کاربری مدیر"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-slate-700"
                >
                  رمز عبور
                </label>
                <div className="relative">
                  <LockIcon className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    dir="ltr"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="h-11 w-full rounded-xl border border-slate-300 bg-white pe-11 ps-10 text-sm text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                    placeholder="رمز عبور"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((current) => !current)}
                    className="absolute end-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
                    aria-label={
                      showPassword ? 'پنهان کردن رمز عبور' : 'نمایش رمز عبور'
                    }
                  >
                    {showPassword ? (
                      <EyeOffIcon className="size-4" />
                    ) : (
                      <EyeIcon className="size-4" />
                    )}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-b from-brand-500 to-brand-600 text-sm font-semibold text-white shadow-md shadow-brand-600/25 transition-all duration-150 hover:from-brand-500 hover:to-brand-700 hover:shadow-lg hover:shadow-brand-600/30 active:translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:pointer-events-none disabled:opacity-60"
              >
                {submitting && <Spinner className="size-4" />}
                {submitting ? 'در حال ورود…' : 'ورود به سیستم'}
              </button>
            </form>

            <p className="mt-6 border-t border-slate-100 pt-4 text-center text-xs leading-5 text-slate-400">
              ایجاد حساب کاربری از طریق این صفحه ممکن نیست. حساب مدیر توسط
              مدیر سیستم ساخته می‌شود.
            </p>
          </div>

          <p className="mt-6 text-center text-xs text-slate-400">
            اطلاعات شخصی و مالی رانندگان محرمانه است؛ دسترسی غیرمجاز ممنوع می‌باشد.
          </p>
        </div>
      </div>
    </div>
  )
}
