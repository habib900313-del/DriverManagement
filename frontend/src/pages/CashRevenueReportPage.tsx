import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRightIcon, CalendarIcon, PrinterIcon, RefreshIcon } from '../components/icons'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../context/ToastContext'
import { fetchCashRevenueReport } from '../lib/api'
import { formatJalaliShort, formatKabulDateTime, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { CashRevenueReport } from '../types/financial'

export function CashRevenueReportPage() {
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<CashRevenueReport | null>(null)
  const [asOf, setAsOf] = useState<string>('')
  const [dateFrom, setDateFrom] = useState<string>('')
  const [dateTo, setDateTo] = useState<string>('')
  const [reportGeneratedAt] = useState(() => new Date().toISOString())
  const { notify } = useToast()

  // Spec F4: the report range must end on or before the report date.
  // Native date inputs require Gregorian ISO values (YYYY-MM-DD), not the
  // Jalali presentation value used elsewhere in the report.
  const reportDate = asOf || reportGeneratedAt.slice(0, 10)

  const load = useCallback(async () => {
    setError(null)
    try {
      const data = await fetchCashRevenueReport(asOf || undefined, dateFrom || undefined, dateTo || undefined)
      setReport(data)
    } catch (cause) {
      if (!isAbortError(cause)) {
        const msg = getErrorMessage(cause)
        setError(msg)
        notify('error', msg)
      }
    }
  }, [asOf, dateFrom, dateTo, notify])

  useEffect(() => {
    load()
  }, [load])

  const printedAt = formatKabulDateTime(reportGeneratedAt)

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
          title="گزارش درآمد نقدی"
          description="مجموع مبالغ نقدی دریافتی از تمام رانندگان، با قابلیت فیلتر تاریخ."
        />

        <form className="space-y-4 p-5" onSubmit={(e) => { e.preventDefault(); load() }}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600" htmlFor="cash-as-of">
                تاریخ محاسبه (اختیاری)
              </label>
              <input
                id="cash-as-of"
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                type="date"
                value={asOf}
                onChange={(e) => setAsOf(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600" htmlFor="cash-from">
                از تاریخ (اختیاری)
              </label>
              <input
                id="cash-from"
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                type="date"
                value={dateFrom}
                max={dateTo || reportDate}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600" htmlFor="cash-to">
                تا تاریخ (اختیاری)
              </label>
              <input
                id="cash-to"
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 dir-ltr focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                type="date"
                value={dateTo}
                max={reportDate}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>

            <div className="flex items-end gap-2">
              <Button type="submit" icon={<CalendarIcon className="size-4" />}>
                نمایش گزارش
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => window.print()}
                icon={<PrinterIcon className="size-4" />}
              >
                چاپ گزارش
              </Button>
            </div>
          </div>

          <p className="text-xs text-slate-500">
            «از تاریخ» و «تا تاریخ» باید با هم انتخاب شوند و پایان بازه نباید بعد از تاریخ محاسبه باشد.
            برای ذخیره گزارش به‌صورت PDF از گزینهٔ «چاپ گزارش» و سپس «Save as PDF» مرورگر استفاده کنید.
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
          {/* ------------------------- on screen ------------------------- */}
          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm print:hidden">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-sm font-semibold text-slate-800">نتایج گزارش</h2>
                <p className="mt-0.5 text-xs text-slate-500">گزارش درآمد نقدی بر اساس معیارهای انتخاب‌شده.</p>
              </div>
            </div>

            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">درآمد نقدی کل</p>
                <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900" dir="ltr">
                  {toPersianDigits(report.cash_revenue)} AFN
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">تعداد کل پرداخت‌ها</p>
                <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900" dir="ltr">
                  {toPersianDigits(report.payment_count.toString())}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">تعداد رانندگان پرداخت‌کننده</p>
                <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900" dir="ltr">
                  {toPersianDigits(report.driver_count.toString())}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">تاریخ گزارش</p>
                <p className="mt-2 text-xl font-bold tracking-tight text-slate-900">
                  {formatJalaliShort(report.as_of)}
                </p>
              </div>
            </section>

            {report.by_month.length > 0 && (
              <div className="p-5">
                <h3 className="text-sm font-semibold text-slate-800">تفکیک درآمد بر اساس ماه</h3>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-100 text-xs text-slate-500">
                      <tr>
                        <th className="px-4 py-2 text-right">ماه</th>
                        <th className="px-4 py-2 text-left">تعداد پرداخت</th>
                        <th className="px-4 py-2 text-left">مجموع درآمد</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {report.by_month.map((row) => (
                        <tr key={row.month}>
                          <td className="px-4 py-2 text-right text-slate-600" dir="ltr">
                            {row.month}
                          </td>
                          <td className="px-4 py-2 text-left" dir="ltr">
                            {toPersianDigits(row.count.toString())}
                          </td>
                          <td className="px-4 py-2 text-left" dir="ltr">
                            {toPersianDigits(row.total)} AFN
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="p-5 bg-slate-50 rounded-xl border border-slate-200">
              <h3 className="text-sm font-semibold text-slate-800">تفکیک تاریخ‌ها</h3>
              <table className="w-full mt-2 text-sm">
                <thead className="bg-slate-100 text-xs text-slate-500">
                  <tr>
                    <th className="px-4 py-2 text-right">فیلد</th>
                    <th className="px-4 py-2 text-left">مقدار</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  <tr>
                    <td className="px-4 py-2 text-right text-slate-600">تاریخ محاسبه</td>
                    <td className="px-4 py-2 text-left">{formatJalaliShort(report.as_of)}</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 text-right text-slate-600">از تاریخ</td>
                    <td className="px-4 py-2 text-left">
                      {report.date_from ? formatJalaliShort(report.date_from) : '—'}
                    </td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 text-right text-slate-600">تا تاریخ</td>
                    <td className="px-4 py-2 text-left">
                      {report.date_to ? formatJalaliShort(report.date_to) : '—'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* -------------------------- print sheet -------------------------- */}
          <section className="print-sheet hidden print:block">
            <header style={{ borderBottom: '2px solid #0f172a', paddingBottom: '8pt', marginBottom: '10pt' }}>
              <h1 style={{ fontSize: '15pt', fontWeight: 700, textAlign: 'center' }}>
                گزارش درآمد مالی
              </h1>
              <p style={{ fontSize: '9pt', textAlign: 'center', color: '#475569', marginTop: '2pt' }}>
                گزارش درآمد نقدی دریافتی از تمام رانندگان
              </p>
            </header>

            <table style={{ marginBottom: '10pt' }}>
              <tbody>
                <tr>
                  <th style={{ width: '30%', textAlign: 'right' }}>از تاریخ</th>
                  <td style={{ textAlign: 'left' }}>
                    {report.date_from ? formatJalaliShort(report.date_from) : 'کل دوره'}
                  </td>
                </tr>
                <tr>
                  <th style={{ textAlign: 'right' }}>تا تاریخ</th>
                  <td style={{ textAlign: 'left' }}>
                    {report.date_to ? formatJalaliShort(report.date_to) : 'کل دوره'}
                  </td>
                </tr>
                <tr>
                  <th style={{ textAlign: 'right' }}>تاریخ محاسبه</th>
                  <td style={{ textAlign: 'left' }}>{formatJalaliShort(report.as_of)}</td>
                </tr>
              </tbody>
            </table>

            <table style={{ marginBottom: '10pt' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'right' }}>شرح</th>
                  <th style={{ textAlign: 'left', width: '30%' }}>مقدار</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ textAlign: 'right' }}>مجموع درآمد نقدی در بازه</td>
                  <td style={{ textAlign: 'left' }} dir="ltr">
                    {toPersianDigits(report.cash_revenue)} AFN
                  </td>
                </tr>
                <tr>
                  <td style={{ textAlign: 'right' }}>تعداد کل پرداخت‌ها</td>
                  <td style={{ textAlign: 'left' }} dir="ltr">
                    {toPersianDigits(report.payment_count.toString())}
                  </td>
                </tr>
                <tr>
                  <td style={{ textAlign: 'right' }}>تعداد رانندگان پرداخت‌کننده</td>
                  <td style={{ textAlign: 'left' }} dir="ltr">
                    {toPersianDigits(report.driver_count.toString())}
                  </td>
                </tr>
                <tr>
                  <td style={{ textAlign: 'right' }}>ثبت حسابرسی</td>
                  <td style={{ textAlign: 'left' }} dir="ltr">
                    {toPersianDigits(report.recorded_as_of_audit)} AFN
                  </td>
                </tr>
              </tbody>
            </table>

            {report.by_month.length > 0 && (
              <table style={{ marginBottom: '10pt' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'right' }}>ماه</th>
                    <th style={{ textAlign: 'left' }}>تعداد پرداخت</th>
                    <th style={{ textAlign: 'left' }}>مجموع درآمد</th>
                  </tr>
                </thead>
                <tbody>
                  {report.by_month.map((row) => (
                    <tr key={row.month}>
                      <td style={{ textAlign: 'right' }} dir="ltr">
                        {row.month}
                      </td>
                      <td style={{ textAlign: 'left' }} dir="ltr">
                        {toPersianDigits(row.count.toString())}
                      </td>
                      <td style={{ textAlign: 'left' }} dir="ltr">
                        {toPersianDigits(row.total)} AFN
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <p style={{ fontSize: '8pt', color: '#64748b', marginTop: '10pt' }}>
              تاریخ تهیه گزارش: {printedAt}
            </p>
          </section>
        </>
      )}
    </div>
  )
}
