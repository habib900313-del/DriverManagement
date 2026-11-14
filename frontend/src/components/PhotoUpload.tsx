import { useEffect, useRef, useState } from 'react'
import { cn } from '../lib/cn'
import { CameraIcon, ImageIcon, XIcon } from './icons'

const MAX_SIZE = 5 * 1024 * 1024
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

interface PhotoUploadProps {
  file: File | null
  existingUrl?: string | null
  onChange: (file: File | null) => void
  error?: string
  disabled?: boolean
}

export function PhotoUpload({
  file,
  existingUrl,
  onChange,
  error,
  disabled = false,
}: PhotoUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (!file) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const accept = (chosen: File) => {
    if (!ALLOWED_TYPES.includes(chosen.type)) {
      setLocalError('فقط تصاویر JPG، JPEG، PNG یا WebP مجاز هستند.')
      onChange(null)
      return
    }
    if (chosen.size > MAX_SIZE) {
      setLocalError('حجم عکس نباید بیشتر از ۵ مگابایت باشد.')
      onChange(null)
      return
    }
    setLocalError(null)
    onChange(chosen)
  }

  const handleInput = (event: React.ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0]
    event.target.value = ''
    if (chosen) accept(chosen)
  }

  const shownError = error ?? localError
  const source = preview ?? existingUrl ?? null

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-slate-700">عکس پروفایل</span>
      <div
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          if (disabled) return
          const dropped = event.dataTransfer.files?.[0]
          if (dropped) accept(dropped)
        }}
        className={cn(
          'flex flex-wrap items-center gap-4 rounded-xl border border-dashed px-4 py-4 transition',
          shownError
            ? 'border-rose-300 bg-rose-50/40'
            : 'border-slate-300 bg-slate-50/60',
          disabled && 'opacity-60',
        )}
      >
        <div className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white">
          {source ? (
            <img
              src={source}
              alt="پیش‌نمایش عکس راننده"
              className="size-full object-cover"
            />
          ) : (
            <ImageIcon className="size-7 text-slate-300" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-700">
            {file
              ? file.name
              : existingUrl
                ? 'عکس فعلی راننده'
                : 'هیچ عکسی انتخاب نشده است'}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            JPG، JPEG، PNG یا WebP — حداکثر ۵ مگابایت
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-50"
            >
              <CameraIcon className="size-4" />
              {source ? 'تغییر عکس' : 'انتخاب عکس'}
            </button>
            {file && (
              <button
                type="button"
                disabled={disabled}
                onClick={() => {
                  setLocalError(null)
                  onChange(null)
                }}
                className="inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:pointer-events-none disabled:opacity-50"
              >
                <XIcon className="size-3.5" />
                حذف انتخاب
              </button>
            )}
          </div>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
          onChange={handleInput}
          className="hidden"
          disabled={disabled}
        />
      </div>
      {shownError && (
        <p className="text-xs text-rose-600" role="alert">
          {shownError}
        </p>
      )}
    </div>
  )
}
