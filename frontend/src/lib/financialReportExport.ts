import type {
  FinancialReport,
  FinancialReportArchiveStatus,
} from '../types/financial'

export const financialReportArchiveLabels: Record<
  FinancialReportArchiveStatus,
  string
> = {
  active: 'رانندگان فعال',
  archived: 'رانندگان آرشیف‌شده',
  all: 'همه رانندگان',
}

function csvCell(value: string | number): string {
  const text = String(value)
  const safeText = /^[=+\-@]/.test(text) ? `'${text}` : text
  return `"${safeText.replace(/"/g, '""')}"`
}

export function buildFinancialReportCsv(report: FinancialReport): string {
  const rows: Array<Array<string | number>> = [
    ['گزارش جامع رانندگان'],
    ['وضعیت رانندگان', financialReportArchiveLabels[report.archive_status]],
    ['تاریخ محاسبه', report.as_of],
    ['از تاریخ', report.date_from ?? 'تمام دوره'],
    ['تا تاریخ', report.date_to ?? 'تمام دوره'],
    [],
    ['شاخص', 'مقدار'],
    ['تعداد پرداخت‌ها', report.payments.count],
    ['مجموع پرداخت‌ها', report.payments.total_amount],
    ['درآمد نقدی', report.revenue.cash_revenue],
    ['ثبت حسابرسی', report.revenue.recorded_as_of_audit],
    ['بدهی کل', report.debt.total_balance],
    ['تعهد جاری', report.debt.current_obligation],
    ['بدهی معوق', report.debt.overdue_debt],
    ['فیس در بازه', report.debt.fee_in_range],
    ['اعتبار در دسترس', report.credit.available_total],
    ['اعتبار تخصیص‌یافته', report.credit.allocated_total],
    ['تعداد رانندگان', report.totals.driver_count],
    ['رانندگان با پایستگی مالی', report.totals.drivers_conserving],
    [],
    [
      'شماره مسلسل',
      'نام راننده',
      'تعداد پرداخت',
      'مجموع پرداخت',
      'بدهی کل',
      'تعهد جاری',
      'بدهی معوق',
      'اعتبار در دسترس',
      'اعتبار تخصیص‌یافته',
      'فیس در بازه',
      'پایستگی مالی',
    ],
    ...report.drivers.map((driver) => [
      driver.driver_code,
      driver.full_name,
      driver.payments_count,
      driver.payments_total,
      driver.total_balance,
      driver.current_obligation,
      driver.overdue_debt,
      driver.available_credit,
      driver.credit_allocated,
      driver.fee_in_range,
      driver.conservation_ok ? 'برقرار' : 'نقض',
    ]),
  ]

  return `\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`
}

export function downloadFinancialReportCsv(report: FinancialReport): void {
  const blob = new Blob([buildFinancialReportCsv(report)], {
    type: 'text/csv;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `financial-report-${report.as_of}-${report.archive_status}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}
