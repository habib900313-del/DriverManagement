import { useEffect, useMemo, useRef, useState } from 'react'
import { cn } from '../lib/cn'
import {
  JALALI_MONTHS,
  WEEKDAY_LABELS,
  buildJalaliMonth,
  formatJalaliShort,
  isoToJalali,
  jalaliToIso,
  jalaliYearOptions,
  shiftJalaliMonth,
  todayIsoKabul,
  toPersianDigits,
} from '../lib/dates'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
} from './icons'

interface JalaliCalendarProps {
  value: string
  onSelect: (iso: string) => void
  onClose: () => void
}

const controlClass =
  'inline-flex size-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900'

export function JalaliCalendar({
  value,
  onSelect,
  onClose,
}: JalaliCalendarProps) {
  const initial =
    isoToJalali(value) ?? isoToJalali(todayIsoKabul()) ?? { jy: 1400, jm: 1, jd: 1 }
  const [view, setView] = useState({ jy: initial.jy, jm: initial.jm })
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handlePointer = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        onClose()
      }
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handlePointer)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handlePointer)
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose])

  const cells = useMemo(() => buildJalaliMonth(view.jy, view.jm), [view])
  const selected = isoToJalali(value)
  const today = isoToJalali(todayIsoKabul())
  const years = useMemo(() => jalaliYearOptions(60), [])

  const handleSelect = (day: number) => {
    onSelect(jalaliToIso(view.jy, view.jm, day))
    onClose()
  }

  return (
    <div ref={containerRef} dir="rtl" role="dialog" aria-label="تقویم شمسی">
      <div className="flex items-center justify-between gap-1">
        <button
          type="button"
          className={controlClass}
          onClick={() => setView(shiftJalaliMonth(view.jy, view.jm, -12))}
          aria-label="سال قبل"
        >
          <ChevronsRightIcon className="size-4" />
        </button>
        <button
          type="button"
          className={controlClass}
          onClick={() => setView(shiftJalaliMonth(view.jy, view.jm, -1))}
          aria-label="ماه قبل"
        >
          <ChevronRightIcon className="size-4" />
        </button>

        <div className="flex flex-1 items-center justify-center gap-1">
          <select
            value={view.jm}
            onChange={(event) =>
              setView((current) => ({
                ...current,
                jm: Number(event.target.value),
              }))
            }
            className="h-8 rounded-lg border border-slate-200 bg-white px-1.5 text-xs font-medium text-slate-700 outline-none focus:border-slate-400"
            aria-label="ماه شمسی"
          >
            {JALALI_MONTHS.map((month, index) => (
              <option key={month} value={index + 1}>
                {month}
              </option>
            ))}
          </select>
          <select
            value={view.jy}
            onChange={(event) =>
              setView((current) => ({
                ...current,
                jy: Number(event.target.value),
              }))
            }
            className="h-8 rounded-lg border border-slate-200 bg-white px-1.5 text-xs font-medium text-slate-700 outline-none focus:border-slate-400"
            aria-label="سال شمسی"
          >
            {years.map((year) => (
              <option key={year} value={year}>
                {toPersianDigits(year)}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          className={controlClass}
          onClick={() => setView(shiftJalaliMonth(view.jy, view.jm, 1))}
          aria-label="ماه بعد"
        >
          <ChevronLeftIcon className="size-4" />
        </button>
        <button
          type="button"
          className={controlClass}
          onClick={() => setView(shiftJalaliMonth(view.jy, view.jm, 12))}
          aria-label="سال بعد"
        >
          <ChevronsLeftIcon className="size-4" />
        </button>
      </div>

      <div className="mt-2 grid grid-cols-7 gap-1 border-b border-slate-100 pb-2">
        {WEEKDAY_LABELS.map((label) => (
          <span
            key={label}
            className="py-1 text-center text-[11px] font-medium text-slate-400"
          >
            {label.slice(0, 2)}
          </span>
        ))}
      </div>

      <div className="mt-1 grid grid-cols-7 gap-1">
        {cells.map((day, index) => {
          if (day === null) {
            return <span key={`empty-${index}`} />
          }
          const isSelected =
            selected?.jy === view.jy &&
            selected?.jm === view.jm &&
            selected?.jd === day
          const isToday =
            today?.jy === view.jy && today?.jm === view.jm && today?.jd === day

          return (
            <button
              key={day}
              type="button"
              onClick={() => handleSelect(day)}
              className={cn(
                'flex aspect-square items-center justify-center rounded-lg text-sm transition',
                isSelected
                  ? 'bg-gradient-to-b from-brand-500 to-brand-600 font-semibold text-white shadow-sm shadow-brand-600/25'
                  : isToday
                    ? 'border border-brand-300 font-semibold text-brand-700 hover:bg-brand-50'
                    : 'text-slate-700 hover:bg-slate-100',
              )}
            >
              {toPersianDigits(day)}
            </button>
          )
        })}
      </div>

      <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2">
        <button
          type="button"
          onClick={() => {
            onSelect(todayIsoKabul())
            onClose()
          }}
          className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
        >
          امروز
        </button>
        <span className="text-[11px] text-slate-400">
          {value ? `انتخاب‌شده: ${formatJalaliShort(value)}` : 'تقویم هجری شمسی'}
        </span>
      </div>
    </div>
  )
}
