import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PlusIcon, RefreshIcon, UsersIcon } from '../components/icons'
import { Button, LinkButton } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import {
  fetchCashRevenueReport,
} from '../lib/api'
import { formatJalaliShort, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'

function MoneyCard({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string
  value: string
  icon: React.ComponentType<{ className?: string }>
  tone: string
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-bold tracking-tight text-slate-900" dir="ltr">
            {toPersianDigits(value)}
          </p>
        </div>
        <span
          className={`flex size-11 items-center justify-center rounded-xl ring-4 ${tone} ring-slate-200`}
        >
          <Icon className="size-5" />
        </span>
      </div>
    </div>
  )
}

export function FinancialDashboardPage() {
  const { notify } = useToast()
  const [report, setReport] = useState<{
    cash_revenue: string
    payment_count: number
  } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const rev = await fetchCashRevenueReport()
      setReport({
        cash_revenue: rev.cash_revenue,
        payment_count: rev.payment_count,
      })
    } catch (cause) {
      if (!isAbortError(cause)) {
        setError(getErrorMessage(cause))
        notify('error', getErrorMessage(cause))
      }
    }
  }, [notify])

  useEffect(() => {
    load()
    return () => {}
  }, [load])

  return (
    <div className="space-y-6">
      <PageHeader
        title="داشبورد مالی"
        description="خلاصه وضعیت مالی، درآمد نقدی، بدهی معوق و اعتبار رانندگان."
        actions={
          <LinkButton
            to="/financial/payments/new"
            icon={<PlusIcon className="size-4" />}
          >
            ثبت پرداخت جدید
          </LinkButton>
        }
      />

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
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

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MoneyCard
          label="درآمد نقدی کل"
          value={report?.cash_revenue ?? '0'}
          icon={UsersIcon}
          tone="bg-emerald-50 text-emerald-600"
        />
        <MoneyCard
          label="تعداد پرداخت‌ها"
          value={report?.payment_count?.toString() ?? '0'}
          icon={UsersIcon}
          tone="bg-slate-900 text-white"
        />
        <MoneyCard
          label="اعتبار قابل استفاده"
          value='0'
          icon={UsersIcon}
          tone="bg-blue-50 text-blue-600"
        />
        <MoneyCard
          label="بدهی معوق کل"
          value='0'
          icon={UsersIcon}
          tone="bg-rose-50 text-rose-600"
        />
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">
              گزارش درآمد نقدی
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              مجموع مبالغ نقدی دریافتی از تمامی رانندگان.
            </p>
          </div>
          <Link
            to="/financial/reports/cash-revenue"
            className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 transition hover:text-slate-900"
          >
            گزارش کامل
            <span>→</span>
          </Link>
        </div>

        <div className="overflow-x-auto p-5">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-5 py-2.5 text-right font-middle">محصول خالص</th>
                <th className="px-5 py-2.5 text-right font-middle">تعداد پرداخت‌ها</th>
                <th className="px-5 py-2.5 text-right font-middle">تاریخ گزارش</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr className="transition hover:bg-slate-50/70">
                <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                  {toPersianDigits(report?.cash_revenue ?? '0')} AFN
                </td>
                <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                  {toPersianDigits(report?.payment_count?.toString() ?? '0')}
                </td>
                <td className="px-5 py-3 text-xs text-slate-500">
                  {formatJalaliShort(new Date().toISOString().split('T')[0])}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">
            عملیات سریع
          </h3>
          <div className="space-y-2">
            <LinkButton
              to="/financial/payments/new"
              icon={<PlusIcon className="size-4" />}
              variant="secondary"
            >
              ثبت پرداخت جدید
            </LinkButton>
            <LinkButton
              to="/financial/history"
              icon={<PlusIcon className="size-4" />}
              variant="secondary"
            >
              سوابق مالی
            </LinkButton>
          </div>
        </div>
      </section>
    </div>
  )
}
