import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { createManagedUser, fetchManagedUsers } from '../lib/api'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { CreateManagedUserInput, ManagedUser } from '../types/auth'
import { Button } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { StatusBadge } from '../components/ui/Badge'

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
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchManagedUsers(controller.signal)
      .then(setUsers)
      .catch((cause) => {
        if (!isAbortError(cause)) setError(getErrorMessage(cause))
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  if (!user?.is_superuser) {
    return <p className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">دسترسی فقط برای Superuser مجاز است.</p>
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

  return (
    <div className="space-y-5" dir="rtl">
      <PageHeader title="مدیریت کاربران" description="ایجاد کاربران عادی سیستم با نقش Admin یا Guest." />
      {error && <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-slate-800">ایجاد کاربر جدید</h2>
          <form className="space-y-4" onSubmit={submit}>
            <Field label="نام کاربری" required>
              <input className="h-10 w-full rounded-lg border border-slate-300 px-3 text-sm" value={form.username} onChange={(e) => update('username', e.target.value)} required autoComplete="off" />
            </Field>
            <Field label="نام کامل" required>
              <input className="h-10 w-full rounded-lg border border-slate-300 px-3 text-sm" value={form.full_name} onChange={(e) => update('full_name', e.target.value)} required />
            </Field>
            <Field label="رمز عبور" required hint="رمز باید با قوانین امنیتی Django سازگار باشد.">
              <input type="password" className="h-10 w-full rounded-lg border border-slate-300 px-3 text-sm" value={form.password} onChange={(e) => update('password', e.target.value)} required autoComplete="new-password" />
            </Field>
            <Field label="تکرار رمز عبور" required>
              <input type="password" className="h-10 w-full rounded-lg border border-slate-300 px-3 text-sm" value={form.password_confirmation} onChange={(e) => update('password_confirmation', e.target.value)} required autoComplete="new-password" />
            </Field>
            <Field label="نقش" required>
              <select className="h-10 w-full rounded-lg border border-slate-300 px-3 text-sm" value={form.role} onChange={(e) => update('role', e.target.value)}>
                <option value="admin">Admin</option>
                <option value="guest">Guest</option>
              </select>
            </Field>
            <Button type="submit" loading={submitting}>ایجاد کاربر</Button>
          </form>
        </section>

        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-5 py-4"><h2 className="text-sm font-semibold text-slate-800">فهرست کاربران</h2></div>
          {loading ? <p className="p-5 text-sm text-slate-500">در حال بارگذاری…</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="px-5 py-3 text-right">نام کاربری</th><th className="px-5 py-3 text-right">نام کامل</th><th className="px-5 py-3 text-right">نقش</th><th className="px-5 py-3 text-right">وضعیت</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((item) => <tr key={item.id}><td className="px-5 py-3 font-mono" dir="ltr">{item.username}</td><td className="px-5 py-3">{item.full_name}</td><td className="px-5 py-3">{item.role === 'superuser' ? 'Superuser' : item.role === 'admin' ? 'Admin' : 'Guest'}</td><td className="px-5 py-3"><StatusBadge active={item.is_active} /></td></tr>)}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
