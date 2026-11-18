import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PlusIcon, RefreshIcon, UsersIcon } from '../components/icons'
import { Button, LinkButton } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { useAuth } from '../context/AuthContext'
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
    <div className="animate-fade-in-up rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-bold tracking-tight text-slate-900" dir="ltr">
            {toPersianDigits(value)}
          </p>
        </div>
        <span
          className={`flex size-11 items-center justify-center rounded-xl shadow-sm ring-1 ring-black/5 ${tone}`}
        >
          <Icon className="size-5" />
        </span>
      </div>
    </div>
  )
}

export function FinancialDashboardPage() {
  const { user } = useAuth()
  const canManage = Boolean(user?.is_staff || user?.is_superuser)
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
        actions={canManage ? (
          <LinkButton
            to="/financial/payments/new"
            icon={<PlusIcon className="size-4" />}
          >
            ثبت پرداخت جدید
          </LinkButton>
        ) : undefined}
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
          tone="bg-gradient-to-br from-brand-500 to-brand-600 text-white"
        />
        <MoneyCard
          label="اعتبار قابل استفاده"
          value='0'
          icon={UsersIcon}
          tone="bg-brand-50 text-brand-600"
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

        <div className="p-5" dir="rtl">
          {/* Shared 3-column grid: header and data row use the exact same template */}
          <div className="grid grid-cols-3 gap-4 rounded-t-lg bg-slate-50 px-5 py-2.5 text-xs text-slate-500">
            <div className="text-right font-medium">محصول خالص</div>
            <div className="text-right font-medium">تعداد پرداخت‌ها</div>
            <div className="text-right font-medium">تاریخ گزارش</div>
          </div>
          <div className="grid grid-cols-3 gap-4 border-b border-slate-100 bg-white px-5 py-3 text-sm transition hover:bg-slate-50/70">
            <div className="text-right font-mono text-xs text-slate-600">
              <span dir="ltr">{toPersianDigits(report?.cash_revenue ?? '0')} AFN</span>
            </div>
            <div className="text-right font-mono text-xs text-slate-600">
              <span dir="ltr">{toPersianDigits(report?.payment_count?.toString() ?? '0')}</span>
            </div>
            <div className="text-right text-xs text-slate-500">
              {formatJalaliShort(new Date().toISOString().split('T')[0])}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">
            عملیات سریع
          </h3>
          <div className="space-y-2">
            {canManage && (
              <LinkButton
                to="/financial/payments/new"
                icon={<PlusIcon className="size-4" />}
                variant="secondary"
              >
                ثبت پرداخت جدید
              </LinkButton>
            )}
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
