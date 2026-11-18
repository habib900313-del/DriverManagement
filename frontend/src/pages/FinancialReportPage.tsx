import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRightIcon,
  CalendarIcon,
  PrinterIcon,
  RefreshIcon,
} from '../components/icons'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import { fetchFinancialReport } from '../lib/api'
import { formatJalaliShort, toPersianDigits, todayIsoKabul } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import {
  downloadFinancialReportCsv,
  financialReportArchiveLabels,
} from '../lib/financialReportExport'
import type { FinancialReport } from '../types/financial'

function MetricCard({
  label,
  value,
  hint,
  tone = 'slate',
}: {
  label: string
  value: string
  hint?: string
  tone?: 'slate' | 'emerald' | 'rose'
}) {
  const toneClass =
    tone === 'emerald' ? 'text-emerald-600' : tone === 'rose' ? 'text-rose-600' : 'text-slate-900'
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-bold tracking-tight ${toneClass}`} dir="ltr">
        {toPersianDigits(value)}
      </p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  )
}

export function FinancialReportPage() {
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<FinancialReport | null>(null)
  const [asOf, setAsOf] = useState<string>(todayIsoKabul())
  const [dateFrom, setDateFrom] = useState<string>('')
  const [dateTo, setDateTo] = useState<string>('')
  const [archiveStatus, setArchiveStatus] =
    useState<FinancialReport['archive_status']>('active')
  const { notify } = useToast()

  // Spec F4: the report range must end on or before the report date, so the
  // pickers are bounded to prevent an invalid combination.
  const reportDate = asOf || todayIsoKabul()

  const load = useCallback(async () => {
    setError(null)
    setReport(null)
    try {
      const data = await fetchFinancialReport(
        asOf || undefined,
        dateFrom || undefined,
        dateTo || undefined,
        archiveStatus,
      )
      setReport(data)
    } catch (cause) {
      if (!isAbortError(cause)) {
        const msg = getErrorMessage(cause)
        setError(msg)
        notify('error', msg)
      }
    }
  }, [archiveStatus, asOf, dateFrom, dateTo, notify])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3 print:hidden">
        <Link
          to="/financial"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition hover:text-slate-900"
        >
          <ArrowRightIcon className="size-4" />
          بازگشت به داشبورد مالی
        </Link>
      </div>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm print:hidden">
        <PageHeader
          title="گزارش مالی جامع"
          description="پرداخت‌ها، درآمد، بدهی‌ها، اعتبارها و وضعیت مالی رانندگان در بازه انتخاب‌شده."
          actions={
            report && (
              <>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => window.print()}
                  icon={<PrinterIcon className="size-4" />}
                >
                  چاپ / ذخیره PDF
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => downloadFinancialReportCsv(report)}
                >
                  دریافت Excel (CSV)
                </Button>
              </>
            )
          }
        />

        <form className="space-y-4 p-5" onSubmit={(e) => { e.preventDefault(); load() }}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600" htmlFor="report-archive-status">
                وضعیت آرشیف رانندگان
              </label>
              <select
                id="report-archive-status"
                className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                value={archiveStatus}
                onChange={(event) => {
                  const value = event.target.value
                  if (value === 'active' || value === 'archived' || value === 'all') {
                    setArchiveStatus(value)
                    setReport(null)
                  }
                }}
              >
                <option value="active">رانندگان فعال</option>
                <option value="archived">رانندگان آرشیف‌شده</option>
                <option value="all">همه رانندگان</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600" htmlFor="report-as-of">
                تاریخ محاسبه (اختیاری)
              </label>
              <input
                id="report-as-of"
                className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                type="date"
                value={asOf}
                onChange={(e) => {
                  setAsOf(e.target.value)
                  setReport(null)
                }}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600" htmlFor="report-from">
                از تاریخ
              </label>
              <input
                id="report-from"
                className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                type="date"
                value={dateFrom}
                max={dateTo || reportDate}
                onChange={(e) => {
                  setDateFrom(e.target.value)
                  setReport(null)
                }}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600" htmlFor="report-to">
                تا تاریخ
              </label>
              <input
                id="report-to"
                className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                type="date"
                value={dateTo}
                max={reportDate}
                onChange={(e) => {
                  setDateTo(e.target.value)
                  setReport(null)
                }}
              />
            </div>

            <div className="flex items-end">
              <Button type="submit" icon={<CalendarIcon className="size-4" />}>
                نمایش گزارش
              </Button>
            </div>
          </div>

          <p className="text-xs text-slate-500">
            «از تاریخ» و «تا تاریخ» باید با هم انتخاب شوند. پرداخت‌ها و درآمد بر اساس همین بازه
            محاسبه می‌شوند؛ بدهی و اعتبار وضعیت راننده در «تاریخ محاسبه» است.
            وضعیت فعال به رانندگان غیروآرشیف‌شده با وضعیت فعال اشاره دارد.
          </p>
        </form>
      </section>

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 print:hidden">
          <p>{error}</p>
          <Button variant="secondary" size="sm" onClick={load} icon={<RefreshIcon className="size-4" />}>
            تلاش دوباره
          </Button>
        </div>
      )}

      {report && (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 print:hidden">
            <MetricCard
              label="پرداخت‌های بازه"
              value={toPersianDigits(report.payments.count.toString())}
              hint={`مجموع ${toPersianDigits(report.payments.total_amount)} AFN`}
            />
            <MetricCard
              label="درآمد نقدی"
              value={toPersianDigits(report.revenue.cash_revenue)}
              hint="درآمد ثبت‌شده در بازه انتخابی"
              tone="emerald"
            />
            <MetricCard
              label="بدهی کل"
              value={toPersianDigits(report.debt.total_balance)}
              hint={`معوق: ${toPersianDigits(report.debt.overdue_debt)}`}
              tone={report.debt.total_balance !== '0.00' ? 'rose' : 'slate'}
            />
            <MetricCard
              label="اعتبار در دسترس"
              value={toPersianDigits(report.credit.available_total)}
              hint={`تخصیص‌یافته: ${toPersianDigits(report.credit.allocated_total)}`}
            />
          </section>

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm print:hidden">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-sm font-semibold text-slate-800">وضعیت مالی رانندگان</h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  {toPersianDigits(report.totals.driver_count.toString())} راننده —{' '}
                  {toPersianDigits(report.totals.drivers_conserving.toString())} راننده پایستگی
                  مالی دارند
                </p>
              </div>
              <p className="text-xs text-slate-500">
                تاریخ محاسبه: {formatJalaliShort(report.as_of)}
              </p>
            </div>

            {report.drivers.length === 0 ? (
              <p className="px-5 py-8 text-center text-sm text-slate-500">
                راننده‌ای برای نمایش وجود ندارد.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-xs text-slate-500">
                    <tr>
                      <th className="px-4 py-2 text-right">راننده</th>
                      <th className="px-4 py-2 text-left">پرداخت‌ها</th>
                      <th className="px-4 py-2 text-left">مجموع پرداخت</th>
                      <th className="px-4 py-2 text-left">بدهی کل</th>
                      <th className="px-4 py-2 text-left">تعهد جاری</th>
                      <th className="px-4 py-2 text-left">بدهی معوق</th>
                      <th className="px-4 py-2 text-left">اعتبار در دسترس</th>
                      <th className="px-4 py-2 text-left">پایستگی</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {report.drivers.map((row) => (
                      <tr key={row.driver_id} className="hover:bg-slate-50">
                        <td className="px-4 py-2 text-right">
                          <Link
                            to={`/financial/drivers/${row.driver_id}`}
                            className="font-medium text-slate-800 hover:text-brand-700"
                          >
                            {row.driver_code}
                          </Link>
                          <span className="block text-xs text-slate-500">{row.full_name}</span>
                        </td>
                        <td className="px-4 py-2 text-left" dir="ltr">
                          {toPersianDigits(row.payments_count.toString())}
                        </td>
                        <td className="px-4 py-2 text-left" dir="ltr">
                          {toPersianDigits(row.payments_total)}
                        </td>
                        <td className="px-4 py-2 text-left" dir="ltr">
                          {toPersianDigits(row.total_balance)}
                        </td>
                        <td className="px-4 py-2 text-left" dir="ltr">
                          {toPersianDigits(row.current_obligation)}
                        </td>
                        <td className="px-4 py-2 text-left" dir="ltr">
                          {toPersianDigits(row.overdue_debt)}
                        </td>
                        <td className="px-4 py-2 text-left" dir="ltr">
                          {toPersianDigits(row.available_credit)}
                        </td>
                        <td className="px-4 py-2 text-left">
                          {row.conservation_ok ? (
                            <span className="text-emerald-600">برقرار</span>
                          ) : (
                            <span className="text-rose-600">نقض</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="print-sheet hidden print:block">
            <header style={{ borderBottom: '2px solid #0f172a', paddingBottom: '8pt', marginBottom: '10pt' }}>
              <h1 style={{ fontSize: '15pt', fontWeight: 700, textAlign: 'center' }}>
                گزارش مالی جامع رانندگان
              </h1>
              <p style={{ fontSize: '9pt', textAlign: 'center', color: '#475569', marginTop: '2pt' }}>
                {financialReportArchiveLabels[report.archive_status]}
              </p>
            </header>

            <table style={{ marginBottom: '10pt' }}>
              <tbody>
                <tr>
                  <th style={{ width: '30%', textAlign: 'right' }}>تاریخ محاسبه</th>
                  <td style={{ textAlign: 'left' }}>{formatJalaliShort(report.as_of)}</td>
                </tr>
                <tr>
                  <th style={{ textAlign: 'right' }}>از تاریخ</th>
                  <td style={{ textAlign: 'left' }}>
                    {report.date_from ? formatJalaliShort(report.date_from) : 'تمام دوره'}
                  </td>
                </tr>
                <tr>
                  <th style={{ textAlign: 'right' }}>تا تاریخ</th>
                  <td style={{ textAlign: 'left' }}>
                    {report.date_to ? formatJalaliShort(report.date_to) : 'تمام دوره'}
                  </td>
                </tr>
              </tbody>
            </table>

            <table style={{ marginBottom: '10pt', fontSize: '8pt' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'right' }}>شاخص</th>
                  <th style={{ textAlign: 'left' }}>مقدار</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>تعداد پرداخت‌ها</td><td dir="ltr">{toPersianDigits(report.payments.count.toString())}</td></tr>
                <tr><td>مجموع پرداخت‌ها</td><td dir="ltr">{toPersianDigits(report.payments.total_amount)} AFN</td></tr>
                <tr><td>درآمد نقدی</td><td dir="ltr">{toPersianDigits(report.revenue.cash_revenue)} AFN</td></tr>
                <tr><td>ثبت حسابرسی</td><td dir="ltr">{toPersianDigits(report.revenue.recorded_as_of_audit)} AFN</td></tr>
                <tr><td>بدهی کل</td><td dir="ltr">{toPersianDigits(report.debt.total_balance)} AFN</td></tr>
                <tr><td>تعهد جاری</td><td dir="ltr">{toPersianDigits(report.debt.current_obligation)} AFN</td></tr>
                <tr><td>بدهی معوق</td><td dir="ltr">{toPersianDigits(report.debt.overdue_debt)} AFN</td></tr>
                <tr><td>فیس در بازه</td><td dir="ltr">{toPersianDigits(report.debt.fee_in_range)} AFN</td></tr>
                <tr><td>اعتبار در دسترس</td><td dir="ltr">{toPersianDigits(report.credit.available_total)} AFN</td></tr>
                <tr><td>اعتبار تخصیص‌یافته</td><td dir="ltr">{toPersianDigits(report.credit.allocated_total)} AFN</td></tr>
                <tr><td>تعداد رانندگان</td><td dir="ltr">{toPersianDigits(report.totals.driver_count.toString())}</td></tr>
                <tr><td>رانندگان با پایستگی مالی</td><td dir="ltr">{toPersianDigits(report.totals.drivers_conserving.toString())}</td></tr>
              </tbody>
            </table>

            <h2 style={{ fontSize: '10pt', fontWeight: 700, margin: '8pt 0 4pt' }}>
              وضعیت مالی رانندگان
            </h2>
            <table style={{ fontSize: '7pt' }}>
              <thead>
                <tr>
                  <th>شماره مسلسل</th>
                  <th>نام راننده</th>
                  <th>پرداخت‌ها</th>
                  <th>مجموع پرداخت</th>
                  <th>بدهی کل</th>
                  <th>تعهد جاری</th>
                  <th>بدهی معوق</th>
                  <th>اعتبار</th>
                  <th>پایستگی</th>
                </tr>
              </thead>
              <tbody>
                {report.drivers.map((row) => (
                  <tr key={row.driver_id}>
                    <td>{row.driver_code}</td>
                    <td>{row.full_name}</td>
                    <td dir="ltr">{toPersianDigits(row.payments_count.toString())}</td>
                    <td dir="ltr">{toPersianDigits(row.payments_total)}</td>
                    <td dir="ltr">{toPersianDigits(row.total_balance)}</td>
                    <td dir="ltr">{toPersianDigits(row.current_obligation)}</td>
                    <td dir="ltr">{toPersianDigits(row.overdue_debt)}</td>
                    <td dir="ltr">{toPersianDigits(row.available_credit)}</td>
                    <td>{row.conservation_ok ? 'برقرار' : 'نقض'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  )
}
