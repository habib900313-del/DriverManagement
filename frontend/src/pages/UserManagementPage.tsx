import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  createManagedUser,
  fetchManagedUsers,
  resetManagedUserPassword,
  updateManagedUser,
} from '../lib/api'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { CreateManagedUserInput, ManagedUser } from '../types/auth'
import { Button } from '../components/ui/Button'
import { Field, inputClass } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { StatusBadge } from '../components/ui/Badge'
import { EyeIcon, EyeOffIcon, XIcon } from '../components/icons'
import { cn } from '../lib/cn'

const initialForm: CreateManagedUserInput = {
  username: '',
  full_name: '',
  password: '',
  password_confirmation: '',
  role: 'guest',
}

export function UserManagementPage() {
  const { user } = useAuth()
  const { notify } = useToast()
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [form, setForm] = useState(initialForm)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [updatingId, setUpdatingId] = useState<number | null>(null)
  const [editingUserId, setEditingUserId] = useState<number | null>(null)
  const [editedFullName, setEditedFullName] = useState('')
  const [editedRole, setEditedRole] = useState<'admin' | 'guest'>('guest')
  const [error, setError] = useState<string | null>(null)
  const [passwordTarget, setPasswordTarget] = useState<ManagedUser | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showPasswordConfirmation, setShowPasswordConfirmation] = useState(false)
  const [confirmPasswordReset, setConfirmPasswordReset] = useState(false)
  const [passwordSubmitting, setPasswordSubmitting] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)

  useEffect(() => {
    if (!user?.is_superuser) return
    const controller = new AbortController()
    fetchManagedUsers(controller.signal)
      .then(setUsers)
      .catch((cause) => {
        if (!isAbortError(cause)) setError(getErrorMessage(cause))
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [user?.is_superuser])

  if (!user?.is_superuser) {
    return <p className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700 shadow-xs">دسترسی فقط برای Superuser مجاز است.</p>
  }

  const update = (key: keyof CreateManagedUserInput, value: string) => {
    setForm((previous) => ({ ...previous, [key]: value }))
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const created = await createManagedUser(form)
      setUsers((previous) => [...previous, created].sort((a, b) => a.username.localeCompare(b.username)))
      setForm(initialForm)
      notify('success', `کاربر ${created.username} با موفقیت ایجاد شد.`)
    } catch (cause) {
      const message = getErrorMessage(cause)
      setError(message)
      notify('error', message)
    } finally {
      setSubmitting(false)
    }
  }

  const startEditing = (item: ManagedUser) => {
    setEditingUserId(item.id)
    setEditedFullName(item.full_name)
    setEditedRole(item.role === 'admin' ? 'admin' : 'guest')
  }

  const saveUser = async (item: ManagedUser) => {
    if (!editedFullName.trim()) {
      setError('نام کامل نمی‌تواند خالی باشد.')
      return
    }
    setUpdatingId(item.id)
    setError(null)
    try {
      const updated = await updateManagedUser(item.id, {
        full_name: editedFullName.trim(),
        role: editedRole,
      })
      setUsers((previous) =>
        previous.map((candidate) => candidate.id === updated.id ? updated : candidate),
      )
      setEditingUserId(null)
      notify('success', `اطلاعات کاربر ${updated.username} به‌روزرسانی شد.`)
    } catch (cause) {
      const message = getErrorMessage(cause)
      setError(message)
      notify('error', message)
    } finally {
      setUpdatingId(null)
    }
  }

  const toggleActive = async (item: ManagedUser) => {
    setUpdatingId(item.id)
    setError(null)
    try {
      const updated = await updateManagedUser(item.id, {
        is_active: !item.is_active,
      })
      setUsers((previous) =>
        previous.map((candidate) => candidate.id === updated.id ? updated : candidate),
      )
      notify(
        'success',
        updated.is_active
          ? `کاربر ${updated.username} فعال شد.`
          : `کاربر ${updated.username} غیرفعال شد.`,
      )
    } catch (cause) {
      const message = getErrorMessage(cause)
      setError(message)
      notify('error', message)
    } finally {
      setUpdatingId(null)
    }
  }

  const closePasswordModal = () => {
    setPasswordTarget(null)
    setNewPassword('')
    setPasswordConfirmation('')
    setShowNewPassword(false)
    setShowPasswordConfirmation(false)
    setConfirmPasswordReset(false)
    setPasswordError(null)
  }

  const savePassword = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!passwordTarget || passwordSubmitting) return
    if (newPassword !== passwordConfirmation) {
      setPasswordError('رمزهای عبور یکسان نیستند.')
      return
    }
    if (!confirmPasswordReset) {
      setPasswordError('پیش از ذخیره، عملیات بازنشانی را تأیید کنید.')
      return
    }

    setPasswordSubmitting(true)
    setPasswordError(null)
    try {
      await resetManagedUserPassword(passwordTarget.id, {
        new_password: newPassword,
        password_confirmation: passwordConfirmation,
      })
      notify('success', `رمز عبور ${passwordTarget.username} با موفقیت تغییر کرد.`)
      closePasswordModal()
    } catch (cause) {
      setPasswordError(getErrorMessage(cause))
    } finally {
      setPasswordSubmitting(false)
    }
  }

  const passwordStrength = (() => {
    const checks = [
      newPassword.length >= 8,
      /[a-z]/.test(newPassword) && /[A-Z]/.test(newPassword),
      /\d/.test(newPassword),
      /[^A-Za-z0-9]/.test(newPassword),
    ]
    const score = checks.filter(Boolean).length
    return {
      score,
      label: !newPassword ? 'رمز وارد نشده' : ['ضعیف', 'ضعیف', 'متوسط', 'قوی', 'بسیار قوی'][score],
      color: score < 2 ? 'bg-rose-500' : score < 3 ? 'bg-amber-500' : 'bg-emerald-500',
    }
  })()

  return (
    <div className="space-y-5" dir="rtl">
      <PageHeader title="مدیریت کاربران" description="ایجاد کاربران عادی سیستم با نقش Admin یا Guest." />
      {error && <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 shadow-xs" role="alert">{error}</p>}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 border-b border-slate-100 pb-3">
            <h2 className="text-sm font-semibold text-slate-800">ایجاد کاربر جدید</h2>
            <p className="mt-0.5 text-xs leading-5 text-slate-500">کاربر تازه با نقش دلخواه بساز و دسترسی او را در فهرست کنار مدیریت کن.</p>
          </div>
          <form className="space-y-4" onSubmit={submit}>
            <Field label="نام کاربری" required>
              <input className={inputClass} value={form.username} onChange={(e) => update('username', e.target.value)} required autoComplete="off" />
            </Field>
            <Field label="نام کامل" required>
              <input className={inputClass} value={form.full_name} onChange={(e) => update('full_name', e.target.value)} required />
            </Field>
            <Field label="رمز عبور" required hint="رمز باید با قوانین امنیتی Django سازگار باشد.">
              <input type="password" className={inputClass} value={form.password} onChange={(e) => update('password', e.target.value)} required autoComplete="new-password" />
            </Field>
            <Field label="تکرار رمز عبور" required>
              <input type="password" className={inputClass} value={form.password_confirmation} onChange={(e) => update('password_confirmation', e.target.value)} required autoComplete="new-password" />
            </Field>
            <Field label="نقش" required>
              <select className={inputClass} value={form.role} onChange={(e) => update('role', e.target.value)}>
                <option value="admin">Admin</option>
                <option value="guest">Guest</option>
              </select>
            </Field>
            <Button type="submit" loading={submitting}>ایجاد کاربر</Button>
          </form>
        </section>

        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-5 py-4"><h2 className="text-sm font-semibold text-slate-800">فهرست کاربران</h2></div>
          {loading ? <p className="p-5 text-sm text-slate-500">در حال بارگذاری…</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-sm">
                <thead className="border-b border-slate-200 bg-slate-50/70 text-xs text-slate-500"><tr><th className="px-5 py-3 text-right font-medium">نام کاربری</th><th className="px-5 py-3 text-right font-medium">نام کامل</th><th className="px-5 py-3 text-right font-medium">نقش</th><th className="px-5 py-3 text-right font-medium">وضعیت</th><th className="px-5 py-3 text-right font-medium">مدیریت</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((item) => {
                    const editing = editingUserId === item.id
                    const isSaving = updatingId === item.id
                    return (
                      <tr key={item.id} className="transition hover:bg-slate-50/70">
                        <td className="px-5 py-3 font-mono" dir="ltr">{item.username}</td>
                        <td className="px-5 py-3">
                          {editing ? (
                            <input
                              className="h-9 w-full min-w-36 rounded-xl border border-slate-300 bg-white px-2 text-sm text-slate-900 shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                              value={editedFullName}
                              onChange={(event) => setEditedFullName(event.target.value)}
                              aria-label={`نام کامل ${item.username}`}
                            />
                          ) : item.full_name}
                        </td>
                        <td className="px-5 py-3">
                          {editing ? (
                            <select
                              className="h-9 rounded-xl border border-slate-300 bg-white px-2 text-sm text-slate-900 shadow-xs outline-none transition hover:border-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
                              value={editedRole}
                              onChange={(event) => {
                                const role = event.target.value
                                if (role === 'admin' || role === 'guest') {
                                  setEditedRole(role)
                                }
                              }}
                              aria-label={`نقش ${item.username}`}
                            >
                              <option value="admin">Admin</option>
                              <option value="guest">Guest</option>
                            </select>
                          ) : item.role === 'superuser' ? 'Superuser' : item.role === 'admin' ? 'Admin' : 'Guest'}
                        </td>
                        <td className="px-5 py-3"><StatusBadge active={item.is_active} /></td>
                        <td className="px-5 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              disabled={updatingId !== null || passwordSubmitting}
                              onClick={() => {
                                setPasswordTarget(item)
                                setNewPassword('')
                                setPasswordConfirmation('')
                                setConfirmPasswordReset(false)
                                setPasswordError(null)
                              }}
                            >
                              مدیریت رمز عبور
                            </Button>
                          {item.role !== 'superuser' && (
                            <div className="flex flex-wrap items-center gap-2">
                              {editing ? (
                                <>
                                  <Button
                                    type="button"
                                    size="sm"
                                    loading={isSaving}
                                    onClick={() => saveUser(item)}
                                  >
                                    ذخیره
                                  </Button>
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="secondary"
                                    disabled={isSaving}
                                    onClick={() => setEditingUserId(null)}
                                  >
                                    لغو
                                  </Button>
                                </>
                              ) : (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="secondary"
                                  disabled={updatingId !== null}
                                  onClick={() => startEditing(item)}
                                >
                                  ویرایش
                                </Button>
                              )}
                              <Button
                                type="button"
                                size="sm"
                                variant={item.is_active ? 'danger' : 'success'}
                                disabled={updatingId !== null}
                                loading={isSaving}
                                onClick={() => toggleActive(item)}
                              >
                                {item.is_active ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                              </Button>
                            </div>
                          )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
      {passwordTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/60 p-3 sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="password-reset-title"
        >
          <section className="my-auto w-full max-w-lg rounded-2xl bg-white shadow-2xl ring-1 ring-slate-900/10">
            <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 sm:px-6">
              <div>
                <h2 id="password-reset-title" className="text-base font-semibold text-slate-900">
                  تغییر رمز عبور
                </h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  رمز جدید برای این حساب تعیین کنید. رمز فعلی نمایش داده نمی‌شود.
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                icon={<XIcon className="size-4" />}
                aria-label="بستن پنجره"
                disabled={passwordSubmitting}
                onClick={closePasswordModal}
              />
            </header>
            <form className="space-y-4 p-5 sm:p-6" onSubmit={savePassword} autoComplete="off">
              <div className="grid gap-3 rounded-xl bg-slate-50 p-3 text-sm sm:grid-cols-2">
                <p><span className="text-slate-500">نام: </span><span className="font-medium text-slate-800">{passwordTarget.full_name}</span></p>
                <p dir="ltr" className="text-right"><span className="text-slate-500">نام کاربری: </span><span className="font-mono font-medium text-slate-800">{passwordTarget.username}</span></p>
              </div>

              <Field label="رمز عبور جدید" required>
                <div className="relative">
                  <input
                    type={showNewPassword ? 'text' : 'password'}
                    className={cn(inputClass, 'pl-12')}
                    value={newPassword}
                    onChange={(event) => {
                      setNewPassword(event.target.value)
                      setPasswordError(null)
                    }}
                    required
                    autoComplete="new-password"
                    dir="ltr"
                    aria-label="رمز عبور جدید"
                  />
                  <button
                    type="button"
                    className="absolute inset-y-0 left-0 flex w-11 items-center justify-center text-slate-500 hover:text-slate-800"
                    onClick={() => setShowNewPassword((visible) => !visible)}
                    aria-label={showNewPassword ? 'مخفی کردن رمز جدید' : 'نمایش رمز جدید'}
                  >
                    {showNewPassword ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
                  </button>
                </div>
                <div className="mt-2 space-y-1">
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-100" aria-label={`قدرت رمز: ${passwordStrength.label}`}>
                    <div
                      className={cn('h-full rounded-full transition-all', passwordStrength.color)}
                      style={{ width: `${passwordStrength.score * 25}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-500">قدرت رمز: {passwordStrength.label}</p>
                </div>
              </Field>

              <Field label="تکرار رمز عبور جدید" required>
                <div className="relative">
                  <input
                    type={showPasswordConfirmation ? 'text' : 'password'}
                    className={cn(inputClass, 'pl-12')}
                    value={passwordConfirmation}
                    onChange={(event) => {
                      setPasswordConfirmation(event.target.value)
                      setPasswordError(null)
                    }}
                    required
                    autoComplete="new-password"
                    dir="ltr"
                    aria-label="تکرار رمز عبور جدید"
                  />
                  <button
                    type="button"
                    className="absolute inset-y-0 left-0 flex w-11 items-center justify-center text-slate-500 hover:text-slate-800"
                    onClick={() => setShowPasswordConfirmation((visible) => !visible)}
                    aria-label={showPasswordConfirmation ? 'مخفی کردن تکرار رمز' : 'نمایش تکرار رمز'}
                  >
                    {showPasswordConfirmation ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
                  </button>
                </div>
              </Field>

              <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
                <input
                  type="checkbox"
                  checked={confirmPasswordReset}
                  onChange={(event) => setConfirmPasswordReset(event.target.checked)}
                  className="mt-1 size-4 rounded border-amber-300 text-brand-600 focus:ring-brand-500"
                />
                <span>تغییر رمز این کاربر را تأیید می‌کنم؛ نشست‌های قبلی او نامعتبر خواهند شد.</span>
              </label>

              {passwordError && (
                <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">
                  {passwordError}
                </p>
              )}

              <div className="flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:justify-end">
                <Button type="button" variant="secondary" disabled={passwordSubmitting} onClick={closePasswordModal}>
                  انصراف
                </Button>
                <Button
                  type="submit"
                  loading={passwordSubmitting}
                  disabled={
                    !confirmPasswordReset ||
                    !newPassword ||
                    !passwordConfirmation ||
                    newPassword !== passwordConfirmation
                  }
                >
                  ذخیره رمز جدید
                </Button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}
