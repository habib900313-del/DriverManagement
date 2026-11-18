import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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
  /**
   * When false the field is Jalali-only: the Gregorian toggle and the
   * Gregorian read-out are hidden and the trigger shows `۱۴۰۵/۰۸/۲۵`.
   */
  allowGregorian?: boolean
  /** Compact layout for dense forms: smaller toggle and a single-line read-out. */
  compact?: boolean
}

type CalendarMode = 'jalali' | 'gregorian'

interface PopupPosition {
  top: number
  left: number
  width: number
}

const POPUP_GAP = 8
const POPUP_MAX_WIDTH = 320
const VIEWPORT_MARGIN = 12
/** Fallback height used before the popup can be measured. */
const POPUP_ESTIMATED_HEIGHT = 360

/**
 * Position the calendar popup relative to its trigger. The popup is rendered in
 * a portal (`position: fixed`), so it is never clipped by `overflow: hidden`
 * ancestors. When there is not enough room below, it flips above the trigger.
 */
function computePosition(rect: DOMRect, height: number): PopupPosition {
  const { innerWidth, innerHeight } = window
  const width = Math.min(POPUP_MAX_WIDTH, innerWidth - VIEWPORT_MARGIN * 2)

  const spaceBelow = innerHeight - rect.bottom - POPUP_GAP
  const spaceAbove = rect.top - POPUP_GAP

  let top = rect.bottom + POPUP_GAP
  if (height > spaceBelow && spaceAbove > spaceBelow) {
    top = rect.top - height - POPUP_GAP
  }
  top = Math.max(
    VIEWPORT_MARGIN,
    Math.min(top, innerHeight - height - VIEWPORT_MARGIN),
  )

  const left = Math.max(
    VIEWPORT_MARGIN,
    Math.min(rect.right - width, innerWidth - width - VIEWPORT_MARGIN),
  )

  return { top, left, width }
}

export function DualDateInput({
  id,
  label,
  value,
  onChange,
  required = false,
  error,
  hint,
  disabled = false,
  allowGregorian = true,
  compact = false,
}: DualDateInputProps) {
  const [mode, setMode] = useState<CalendarMode>('jalali')
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<PopupPosition | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popupRef = useRef<HTMLDivElement>(null)
  const close = useCallback(() => setOpen(false), [])
  const valid = isValidIsoDate(value)
  const activeMode: CalendarMode = allowGregorian ? mode : 'jalali'

  const handleToggle = () => {
    if (open) {
      setOpen(false)
      return
    }
    const trigger = triggerRef.current
    if (trigger) {
      setPosition(
        computePosition(trigger.getBoundingClientRect(), POPUP_ESTIMATED_HEIGHT),
      )
    }
    setOpen(true)
  }

  // Refine the position once the popup is mounted and its real height is known.
  useLayoutEffect(() => {
    if (!open) {
      setPosition(null)
      return
    }
    const trigger = triggerRef.current
    const popup = popupRef.current
    if (!trigger || !popup) return
    setPosition(
      computePosition(trigger.getBoundingClientRect(), popup.offsetHeight),
    )
  }, [open])

  // Keep the popup anchored while the viewport scrolls or resizes.
  useEffect(() => {
    if (!open) return
    const reposition = () => {
      const trigger = triggerRef.current
      if (!trigger) return
      setPosition(
        computePosition(
          trigger.getBoundingClientRect(),
          popupRef.current?.offsetHeight ?? POPUP_ESTIMATED_HEIGHT,
        ),
      )
    }
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [open])

  return (
    <Field label={label} htmlFor={id} required={required} error={error} hint={hint}>
      {allowGregorian && (
        <div className={cn('flex items-center justify-between gap-2', compact && 'mb-1')}>
          <div
            className={cn(
              'inline-flex border border-slate-200 bg-slate-50',
              compact
                ? 'rounded-lg p-px text-[11px]'
                : 'rounded-xl p-0.5 text-xs',
            )}
          >
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
                  'font-medium transition',
                  compact ? 'rounded-md px-2 py-0.5' : 'rounded-lg px-2.5 py-1',
                  mode === option.key
                    ? 'bg-white text-brand-700 shadow-xs ring-1 ring-slate-200'
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
      )}

      <div className="relative">
        {activeMode === 'jalali' ? (
          <>
            <button
              id={id}
              ref={triggerRef}
              type="button"
              disabled={disabled}
              onClick={handleToggle}
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
                {valid
                  ? allowGregorian
                    ? formatJalaliLong(value)
                    : formatJalaliShort(value)
                  : 'انتخاب تاریخ شمسی'}
              </span>
              <CalendarIcon className="size-4 text-slate-400" />
            </button>
            {open &&
              position &&
              createPortal(
                <div
                  ref={popupRef}
                  dir="rtl"
                  style={{
                    position: 'fixed',
                    top: position.top,
                    left: position.left,
                    width: position.width,
                    maxHeight: 'calc(100vh - 24px)',
                  }}
                  className="z-[1000] overflow-y-auto rounded-xl border border-slate-200 bg-white p-3 shadow-xl shadow-slate-900/10"
                >
                  <JalaliCalendar
                    value={value}
                    onSelect={onChange}
                    onClose={close}
                  />
                </div>,
                document.body,
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

      {compact ? (
        <p className="mt-1 truncate text-[11px] leading-4 text-slate-400">
          شمسی:{' '}
          <span className="font-medium text-slate-500">
            {valid ? formatJalaliShort(value) : '—'}
          </span>
          {' · '}
          میلادی:{' '}
          <span className="font-medium text-slate-500" dir="ltr">
            {valid ? formatGregorianShort(value) : '—'}
          </span>
        </p>
      ) : (
        <div
          className={cn(
            'grid gap-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-100',
            allowGregorian ? 'grid-cols-2' : 'grid-cols-1',
          )}
        >
          <div>
            <span className="text-slate-400">شمسی: </span>
            <span className="font-medium">
              {valid ? formatJalaliLong(value) : '—'}
            </span>
          </div>
          {allowGregorian && (
            <div>
              <span className="text-slate-400">میلادی: </span>
              <span className="font-medium" dir="ltr">
                {valid ? formatGregorianShort(value) : '—'}
              </span>
            </div>
          )}
        </div>
      )}
    </Field>
  )
}
