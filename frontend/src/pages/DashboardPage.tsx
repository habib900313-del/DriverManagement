import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { DriverAvatar } from '../components/DriverAvatar'
import {
  AlertCircleIcon,
  CheckCircleIcon,
  ChevronLeftIcon,
  PlusIcon,
  RefreshIcon,
  UsersIcon,
} from '../components/icons'
import { StatusBadge } from '../components/ui/Badge'
import { Button, LinkButton } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { PageHeader } from '../components/ui/PageHeader'
import { useAuth } from '../context/AuthContext'
import { fetchDriverStats } from '../lib/api'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { DriverStats } from '../types/driver'

export function DashboardPage() {
  const { user } = useAuth()
  const canManage = Boolean(user?.is_staff || user?.is_superuser)
  const [stats, setStats] = useState<DriverStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true)
    setError(null)
    fetchDriverStats(signal)
      .then((data) => setStats(data))
      .catch((cause) => {
        if (!isAbortError(cause)) setError(getErrorMessage(cause))
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  const cards = [
    {
      label: 'کل رانندگان',
      value: stats?.total ?? 0,
      icon: UsersIcon,
      wrapper:
        'bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-md shadow-brand-600/25 ring-1 ring-brand-500/30',
      labelClass: 'text-brand-100',
      valueClass: 'text-white',
      iconWrap: 'bg-white/15 text-white ring-1 ring-white/25',
    },
    {
      label: 'رانندگان فعال',
      value: stats?.active ?? 0,
      icon: CheckCircleIcon,
      wrapper: 'bg-white ring-1 ring-slate-200',
      labelClass: 'text-slate-500',
      valueClass: 'text-slate-900',
      iconWrap: 'bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100',
    },
    {
      label: 'رانندگان غیرفعال',
      value: stats?.inactive ?? 0,
      icon: AlertCircleIcon,
      wrapper: 'bg-white ring-1 ring-slate-200',
      labelClass: 'text-slate-500',
      valueClass: 'text-slate-900',
      iconWrap: 'bg-amber-50 text-amber-600 ring-1 ring-amber-100',
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title="داشبورد"
        description={`خوش آمدید ${user?.display_name ?? ''}. خلاصه وضعیت رانندگان در یک نگاه.`}
        actions={canManage ? (
          <LinkButton
            to="/drivers/new"
            icon={<PlusIcon className="size-4" />}
          >
            ثبت راننده جدید
          </LinkButton>
        ) : undefined}
      />

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <p>{error}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => load()}
            icon={<RefreshIcon className="size-4" />}
          >
            تلاش دوباره
          </Button>
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map((card, index) => {
          const Icon = card.icon
          return (
            <div
              key={card.label}
              style={{ animationDelay: `${index * 60}ms` }}
              className={`animate-fade-in-up rounded-2xl p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${card.wrapper}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className={`text-sm font-medium ${card.labelClass}`}>
                    {card.label}
                  </p>
                  <p
                    className={`mt-2 text-3xl font-bold tracking-tight ${card.valueClass}`}
                  >
                    {loading && !stats ? (
                      <span className="inline-block h-9 w-16 animate-pulse rounded-lg bg-slate-200/70" />
                    ) : (
                      toPersianDigits(card.value)
                    )}
                  </p>
                </div>
                <span
                  className={`flex size-11 items-center justify-center rounded-xl ${card.iconWrap}`}
                >
                  <Icon className="size-5" />
                </span>
              </div>
            </div>
          )
        })}
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">
              آخرین رانندگان ثبت‌شده
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              پنج راننده‌ای که اخیراً در سیستم ثبت شده‌اند.
            </p>
          </div>
          <Link
            to="/drivers"
            className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 transition hover:text-slate-900"
          >
            مشاهده همه رانندگان
            <ChevronLeftIcon className="size-4" />
          </Link>
        </div>

        {loading && !stats ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 4 }, (_, index) => (
              <div
                key={index}
                className="flex animate-pulse items-center gap-3"
              >
                <div className="size-10 rounded-full bg-slate-100" />
                <div className="h-4 flex-1 rounded bg-slate-100" />
                <div className="h-4 w-24 rounded bg-slate-100" />
              </div>
            ))}
          </div>
        ) : stats && stats.recent.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2.5 text-right font-medium">راننده</th>
                  <th className="px-5 py-2.5 text-right font-medium">
                    شماره مسلسل
                  </th>
                  <th className="px-5 py-2.5 text-right font-medium">پلیت موتر</th>
                  <th className="px-5 py-2.5 text-right font-medium">وضعیت</th>
                  <th className="px-5 py-2.5 text-right font-medium">
                    تاریخ ثبت
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {stats.recent.map((driver) => (
                  <tr key={driver.id} className="transition hover:bg-slate-50/70">
                    <td className="px-5 py-3">
                      <Link
                        to={`/drivers/${driver.id}`}
                        className="flex items-center gap-3"
                      >
                        <DriverAvatar
                          src={driver.photo_url}
                          name={driver.full_name}
                          className="size-9 rounded-full text-xs"
                        />
                        <span className="font-medium text-slate-800 hover:text-slate-950">
                          {driver.full_name}
                        </span>
                      </Link>
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                      {driver.driver_code}
                    </td>
                    <td className="px-5 py-3">
                      <Link
                        to={`/drivers/${driver.id}`}
                        className="font-mono text-xs text-slate-600 hover:text-slate-900"
                        dir="ltr"
                      >
                        {driver.plate_number}
                      </Link>
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge active={driver.status} />
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-500">
                      {formatJalaliShort(driver.registration_date)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={<UsersIcon className="size-6" />}
            title="هنوز راننده‌ای ثبت نشده است"
            description="برای شروع، اولین راننده را با شماره مسلسل دستی ثبت کنید."
            action={canManage ? (
              <LinkButton
                to="/drivers/new"
                size="sm"
                icon={<PlusIcon className="size-4" />}
              >
                ثبت اولین راننده
              </LinkButton>
            ) : undefined}
          />
        )}
      </section>
    </div>
  )
}
