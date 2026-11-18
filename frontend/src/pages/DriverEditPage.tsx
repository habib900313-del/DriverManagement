import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DriverForm } from '../components/DriverForm'
import {
  AlertCircleIcon,
  ArrowRightIcon,
  RefreshIcon,
} from '../components/icons'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { Spinner } from '../components/ui/Spinner'
import { fetchDriver } from '../lib/api'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { Driver } from '../types/driver'

export function DriverEditPage() {
  const { id } = useParams()
  const driverId = Number(id)
  const [driver, setDriver] = useState<Driver | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (!Number.isInteger(driverId) || driverId <= 0) {
      setError('شناسه راننده معتبر نیست.')
      setLoading(false)
      return
    }

    let active = true
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    fetchDriver(driverId, controller.signal)
      .then((data) => {
        if (active) setDriver(data)
      })
      .catch((cause) => {
        if (active && !isAbortError(cause)) setError(getErrorMessage(cause))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [driverId, reloadKey])

  if (loading) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm">
        <Spinner className="size-7" />
        <p className="text-sm">در حال دریافت اطلاعات راننده…</p>
      </div>
    )
  }

  if (error || !driver) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-rose-200 bg-rose-50 px-6 py-14 text-center">
        <AlertCircleIcon className="size-8 text-rose-400" />
        <p className="text-sm text-rose-700">
          {error ?? 'راننده مورد نظر یافت نشد.'}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setReloadKey((current) => current + 1)}
            icon={<RefreshIcon className="size-4" />}
          >
            تلاش دوباره
          </Button>
          <Link
            to="/drivers"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-600 transition hover:bg-white/60"
          >
            <ArrowRightIcon className="size-4" />
            بازگشت به فهرست
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="ویرایش راننده"
        description={`ویرایش اطلاعات «${driver.full_name}». شماره مسلسل به‌صورت پیش‌فرض قفل است و فقط با اقدام صریح مدیر قابل تغییر است.`}
        actions={
          <Link
            to={`/drivers/${driver.id}`}
            className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
          >
            <ArrowRightIcon className="size-4" />
            بازگشت به پروفایل
          </Link>
        }
      />
      <DriverForm key={driver.id} mode="edit" driver={driver} />
    </div>
  )
}
