import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRightIcon, RefreshIcon } from '../components/icons'
import { Button } from '../components/ui/Button'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  fetchAdjustments,
  fetchFeeSchedule,
  fetchDriverFeeHistory,
} from '../lib/api'
import { formatJalaliShort, formatKabulDateTime, toPersianDigits } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'

export function FinancialHistoryPage() {
  const { user } = useAuth()
  const { notify } = useToast()
  const [error, setError] = useState<string | null>(null)
  const [adjustments, setAdjustments] = useState<any[]>([])
  const [feeSchedule, setFeeSchedule] = useState<any[]>([])
  const [feeHistory, setFeeHistory] = useState<any[]>([])

  const load = useCallback(async () => {
    setError(null)
    try {
      const [adjs, fees, hist] = await Promise.all([
        fetchAdjustments(undefined, undefined),
        fetchFeeSchedule(undefined),
        fetchDriverFeeHistory(user!.id, undefined),
      ])
      setAdjustments(adjs)
      setFeeSchedule(fees)
      setFeeHistory(hist)
    } catch (cause) {
      if (!isAbortError(cause)) {
        const msg = getErrorMessage(cause)
        setError(msg)
        notify('error', msg)
      }
    }
  }, [notify])

  useEffect(() => {
    load()
    return () => {}
  }, [load])

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <Link
          to="/financial"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition hover:text-slate-900"
        >
          <ArrowRightIcon className="size-4" />
          بازگشت به داشبورد مالی
        </Link>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <p>{error}</p>
          <Button variant="secondary" size="sm" onClick={load} icon={<RefreshIcon className="size-4" />}>
            تلاش دوباره
          </Button>
        </div>
      )}

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">تعدیل‌ها (بخشش و انتقال)</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              سوابق تغییرات بدهی Ranنده‌ها.
            </p>
          </div>
        </div>

        {adjustments.length === 0 ? (
          <div className="p-5 text-center text-sm text-slate-500">
            هیچ تعدیلی ثبت نشده است.
          </div>
        ) : (
          <div className="overflow-x-auto p-5">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2.5 text-right font-medium">نوع</th>
                  <th className="px-5 py-2.5 text-right font-middle" dir="ltr">مبلغ</th>
                  <th className="px-5 py-2.5 text-right font-middle">دوره مبدأ</th>
                  <th className="px-5 py-2.5 text-right font-middle">دوره مقصد</th>
                  <th className="px-5 py-2.5 text-right font-middle">تاریخ تأثیر</th>
                  <th className="px-5 py-2.5 text-right font-middle">کاربر</th>
                  <th className="px-5 py-2.5 text-left text-sm text-slate-500">دلیل</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {adjustments.map((a: any, idx: number) => (
                  <tr key={idx} className="transition hover:bg-slate-50/70">
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {a.type_label}
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                      {toPersianDigits(a.amount)} AFN
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {formatJalaliShort(a.source_period_start)} تا {formatJalaliShort(a.source_period_end)}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {a.destination_period_start ? `${formatJalaliShort(a.destination_period_start)} تا ${formatJalaliShort(a.destination_period_end)}` : '—'}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {formatJalaliShort(a.effective_date)}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {a.created_by_name}
                    </td>
                    <td className="px-5 py-3 text-left text-xs text-slate-500">
                      {a.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm mt-4">
        <div className="flex flex-wrap items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">برنامه فیس</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              تاریخچه تغییرات مبلغ فیس دوره‌ای.
            </p>
          </div>
        </div>

        {feeSchedule.length === 0 ? (
          <div className="p-5 text-center text-sm text-slate-500">
            هیچ Program فیسی ثبت نشده است.
          </div>
        ) : (
          <div className="overflow-x-auto p-5">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2.5 text-right font-middle" dir="ltr">مبلغ فیس</th>
                  <th className="px-5 py-2.5 text-right font-middle">تاریخ اثر</th>
                  <th className="px-5 py-2.5 text-right font-middle">دلیل</th>
                  <th className="px-5 py-2.5 text-right font-middle">کاربر</th>
                  <th className="px-5 py-2.5 text-left text-sm text-slate-500">تاریخ ثبت</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {feeSchedule.map((f: any, idx: number) => (
                  <tr key={idx} className="transition hover:bg-slate-50/70">
                    <td className="px-5 py-3 font-mono text-xs text-slate-600" dir="ltr">
                      {toPersianDigits(f.amount)} AFN
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {formatJalaliShort(f.effective_from)}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {f.reason}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {f.created_by_name}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-500">
                      {formatKabulDateTime(f.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm mt-4">
        <div className="flex flex-wrap items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">تغییر تاریخ شروع فیس Ranنده</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              سوابق تغییر تاریخ شروع فیس.
            </p>
          </div>
        </div>

        {feeHistory.length === 0 ? (
          <div className="p-5 text-center text-sm text-slate-500">
            هیچ تغییری در تاریخ شروع فیس ثبت نشده است.
          </div>
        ) : (
          <div className="overflow-x-auto p-5">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2.5 text-right font-middle">تاریخ قبلی</th>
                  <th className="px-5 py-2.5 text-right font-middle">تاریخ درخواستی</th>
                  <th className="px-5 py-2.5 text-right font-middle">تاثیرweizer (فعلی)</th>
                  <th className="px-5 py-2.5 text-right font-middle">تاریخ تغییر</th>
                  <th className="px-5 py-2.5 text-left text-sm text-slate-500">دلیل</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {feeHistory.map((h: any, idx: number) => (
                  <tr key={idx} className="transition hover:bg-slate-50/70">
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {h.old_fee_start_date ? formatJalaliShort(h.old_fee_start_date) : '—'}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {formatJalaliShort(h.requested_fee_start_date)}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {formatJalaliShort(h.effective_fee_start_date)}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-600">
                      {formatJalaliShort(h.changed_at)}
                    </td>
                    <td className="px-5 py-3 text-left text-xs text-slate-500">
                      {h.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}