import { useCallback, useState } from 'react'
import { cn } from '../lib/cn'
import {
  formatGregorianShort,
  formatJalaliLong,
  formatJalaliShort,
  isValidIsoDate,
} from '../lib/dates'
import { CalendarIcon } from './icons'
import { JalaliCalendar } from './JalaliCalendar'
import { Field, inputClass } from './ui/Field'

interface DualDateInputProps {
  id?: string
  label: string
  value: string
  onChange: (iso: string) => void
  required?: boolean
  error?: string
  hint?: string
  disabled?: boolean
}

type CalendarMode = 'jalali' | 'gregorian'

export function DualDateInput({
  id,
  label,
  value,
  onChange,
  required = false,
  error,
  hint,
  disabled = false,
}: DualDateInputProps) {
  const [mode, setMode] = useState<CalendarMode>('jalali')
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])
  const valid = isValidIsoDate(value)

  return (
    <Field label={label} htmlFor={id} required={required} error={error} hint={hint}>
      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 text-xs">
          {(
            [
              { key: 'jalali', label: 'شمسی' },
              { key: 'gregorian', label: 'میلادی' },
            ] as const
          ).map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setMode(option.key)}
              className={cn(
                'rounded-md px-2.5 py-1 font-medium transition',
                mode === option.key
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        {valid && (
          <span className="text-[11px] text-slate-400">
            {formatJalaliShort(value)}
          </span>
        )}
      </div>

      <div className="relative">
        {mode === 'jalali' ? (
          <>
            <button
              id={id}
              type="button"
              disabled={disabled}
              onClick={() => setOpen((current) => !current)}
              onMouseDown={(event) => event.stopPropagation()}
              aria-haspopup="dialog"
              aria-expanded={open}
              className={cn(
                inputClass,
                'flex items-center justify-between text-right',
                !valid && 'text-slate-400',
              )}
            >
              <span>
                {valid ? formatJalaliLong(value) : 'انتخاب تاریخ شمسی'}
              </span>
              <CalendarIcon className="size-4 text-slate-400" />
            </button>
            {open && (
              <div className="absolute end-0 top-full z-40 mt-2 w-[min(20rem,calc(100vw-3rem))] rounded-xl border border-slate-200 bg-white p-3 shadow-xl shadow-slate-900/10">
                <JalaliCalendar value={value} onSelect={onChange} onClose={close} />
              </div>
            )}
          </>
        ) : (
          <input
            id={id}
            type="date"
            dir="ltr"
            min="1900-01-01"
            max="2100-12-31"
            value={valid ? value : ''}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            className={cn(inputClass, 'text-left')}
          />
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <div>
          <span className="text-slate-400">شمسی: </span>
          <span className="font-medium">
            {valid ? formatJalaliLong(value) : '—'}
          </span>
        </div>
        <div>
          <span className="text-slate-400">میلادی: </span>
          <span className="font-medium" dir="ltr">
            {valid ? formatGregorianShort(value) : '—'}
          </span>
        </div>
      </div>
    </Field>
  )
}
