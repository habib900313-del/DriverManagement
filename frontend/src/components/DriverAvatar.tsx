import { useEffect, useState, useRef } from 'react'
import { cn } from '../lib/cn'

interface DriverAvatarProps {
  src?: string | null
  name: string
  className?: string
}

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (!words.length) return '؟'
  return words
    .slice(0, 2)
    .map((word) => word.charAt(0))
    .join('')
}

export function DriverAvatar({ src, name, className }: DriverAvatarProps) {
  const errorRef = useRef(false)
  const srcRef = useRef(src)

  useEffect(() => {
    if (srcRef.current !== src) {
      errorRef.current = false
      srcRef.current = src
    }
  }, [src])

  const [failed, setFailed] = useState(false)

  // Sync failed state from ref after render to avoid refs during render warning
  useEffect(() => {
    setFailed(errorRef.current)
  }, [])

  if (src && !failed) {
    return (
      <img
        src={src}
        alt={name}
        onError={() => {
          errorRef.current = true
          setFailed(true)
        }}
        className={cn('shrink-0 object-cover', className)}
        loading="lazy"
      />
    )
  }

  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-center bg-slate-100 font-semibold text-slate-500',
        className,
      )}
      aria-hidden="true"
    >
      {initials(name)}
    </div>
  )
}