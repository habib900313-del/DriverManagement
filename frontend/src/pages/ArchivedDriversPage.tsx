import { useEffect, useState } from 'react'
import { ArchiveIcon, AlertCircleIcon, RefreshIcon, RestoreIcon } from '../components/icons'
import { Button, LinkButton } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { PageHeader } from '../components/ui/PageHeader'
import { Pagination } from '../components/ui/Pagination'
import { Spinner } from '../components/ui/Spinner'
import { useToast } from '../context/ToastContext'
import { fetchArchivedDrivers, restoreDriver } from '../lib/api'
import { formatKabulDateTime, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { Driver, PaginatedResponse } from '../types/driver'

const PAGE_SIZE = 25

export function ArchivedDriversPage() {
  const [page, setPage] = useState(1)
  const [data, setData] = useState<PaginatedResponse<Driver> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const { notify } = useToast()

  useEffect(() => {
    let active = true
    const controller = new AbortController()

    fetchArchivedDrivers(page, PAGE_SIZE, controller.signal)
      .then((response) => {
        if (!active) return
        const totalPages = Math.max(1, Math.ceil(response.count / PAGE_SIZE))
        if (page > totalPages) {
          setLoading(true)
          setPage(totalPages)
          return
        }
        setData(response)
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
  }, [page, reloadKey])

  const handleRestore = async (driver: Driver) => {
    if (busyId !== null) return
    setBusyId(driver.id)
    try {
      await restoreDriver(driver.id)
      notify('success', `راننده «${driver.full_name}» از آرشیف بازگردانده شد.`)
      setLoading(true)
      setError(null)
      setReloadKey((current) => current + 1)
    } catch (cause) {
      notify('error', getErrorMessage(cause))
    } finally {
      setBusyId(null)
    }
  }

  const handlePageChange = (nextPage: number) => {
    setLoading(true)
    setError(null)
    setPage(nextPage)
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1

  return (
    <div className="space-y-5">
      <PageHeader
        title="رانندگان آرشیف‌شده"
        description="این رانندگان از فهرست و جستجوی عادی پنهان هستند؛ سوابق مالی و اسناد آن‌ها حفظ می‌شود."
        actions={
          <LinkButton to="/drivers" variant="secondary">
            فهرست رانندگان فعال
          </LinkButton>
        }
      />

      {data && (
        <p className="text-xs font-medium text-slate-500">
          {toPersianDigits(data.count)} رانندهٔ آرشیف‌شده
        </p>
      )}

      {loading && (
        <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-12 text-sm text-slate-500 shadow-sm">
          <Spinner className="size-4 text-brand-500" />
          در حال دریافت رانندگان آرشیف‌شده…
        </div>
      )}

      {error && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 px-6 py-12 text-center shadow-xs">
          <AlertCircleIcon className="size-7 text-rose-400" />
          <p className="text-sm text-rose-700">{error}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setLoading(true)
              setError(null)
              setReloadKey((current) => current + 1)
            }}
            icon={<RefreshIcon className="size-4" />}
          >
            تلاش دوباره
          </Button>
        </div>
      )}

      {!loading && !error && data?.results.length === 0 && (
        <EmptyState
          icon={<ArchiveIcon className="size-6" />}
          title="رانندهٔ آرشیف‌شده‌ای وجود ندارد"
          description="رانندگانی که آرشیف شوند در این بخش نمایش داده می‌شوند."
        />
      )}

      {!loading && !error && data && data.results.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b border-slate-200 bg-slate-50/70 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3 text-right font-medium">شماره مسلسل</th>
                  <th className="px-4 py-3 text-right font-medium">نام راننده</th>
                  <th className="px-4 py-3 text-right font-medium">پلیت موتر</th>
                  <th className="px-4 py-3 text-right font-medium">زمان آرشیف</th>
                  <th className="px-4 py-3 text-left font-medium">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.results.map((driver) => (
                  <tr key={driver.id} className="transition hover:bg-slate-50/70">
                    <td className="px-4 py-3 font-mono text-xs" dir="ltr">
                      {driver.driver_code}
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {driver.full_name}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" dir="ltr">
                      {driver.plate_number}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {driver.deleted_at
                        ? formatKabulDateTime(driver.deleted_at)
                        : '—'}
                    </td>
                    <td className="px-4 py-3 text-left">
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={busyId === driver.id}
                        disabled={busyId !== null}
                        onClick={() => handleRestore(driver)}
                        icon={<RestoreIcon className="size-4" />}
                      >
                        بازگردانی
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={data.count}
            onChange={handlePageChange}
          />
        </div>
      )}
    </div>
  )
}
