import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DualDateInput } from '../components/DualDateInput'
import { PhotoUpload } from '../components/PhotoUpload'
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  CheckIcon,
  CloudUploadIcon,
  LockIcon,
  UnlockIcon,
  XCircleIcon,
  XIcon,
} from '../components/icons'
import { Button } from '../components/ui/Button'
import { Field, inputClass, textareaClass } from '../components/ui/Field'
import { useToast } from '../context/ToastContext'
import {
  ApiError,
  checkDriverUnique,
  createDriver,
  uploadDocuments,
  updateDriver,
} from '../lib/api'
import { cn } from '../lib/cn'
import {
  formatGregorianShort,
  formatJalaliLong,
  isValidIsoDate,
  isValidJalaliQuarterPeriod,
  jalaliQuarterEnd,
  todayIsoKabul,
} from '../lib/dates'
import { getErrorMessage, normalizeDigits } from '../lib/errors'
import type { Driver, DriverField, DriverPayload } from '../types/driver'

type FormValues = Omit<DriverPayload, 'photo' | 'documents'>
type FormErrors = Partial<Record<DriverField, string>>
type InitialPaymentErrors = Partial<Record<'amount' | 'date' | 'periodStart', string>>

interface DriverFormProps {
  mode: 'create' | 'edit'
  driver?: Driver
}

interface DriverFormProps {
  mode: 'create' | 'edit'
  driver?: Driver
}

function initialValues(driver?: Driver): FormValues {
  return {
    driver_code: driver?.driver_code ?? '',
    full_name: driver?.full_name ?? '',
    father_name: driver?.father_name ?? '',
    phone: driver?.phone ?? '',
    tazkira_number: driver?.tazkira_number ?? '',
    plate_number: driver?.plate_number ?? '',
    address: driver?.address ?? '',
    registration_date: driver?.registration_date ?? todayIsoKabul(),
    fee_start_date: driver?.fee_start_date ?? todayIsoKabul(),
    status: driver?.status ?? true,
  }
}

function validate(
  values: FormValues,
  requireRegistrationDetails: boolean,
): FormErrors {
  const errors: FormErrors = {}

  if (!values.driver_code.trim()) {
    errors.driver_code = 'شمارهسلسل الزامی است و باید دستی وارد شود.'
  }
  if (!values.full_name.trim()) {
    errors.full_name = 'نام کامل الزامی است.'
  }
  if (requireRegistrationDetails) {
    if (!values.father_name.trim()) {
      errors.father_name = 'نام پدر الزامی است.'
    }
    if (!values.phone.trim()) {
      errors.phone = 'شماره تماس الزامی است.'
    }
    if (!values.tazkira_number.trim()) {
      errors.tazkira_number = 'شماره تذکره الزامی است.'
    }
  }
  if (!values.plate_number.trim()) {
    errors.plate_number = 'پلیت موتر الزامی است.'
  }

  return errors
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-4 border-b border-slate-100 pb-3">
        <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
        {description && (
          <p className="mt-0.5 text-xs leading-5 text-slate-500">
            {description}
          </p>
        )}
      </div>
      {children}
    </section>
  )
}

export function DriverForm({ mode, driver }: DriverFormProps) {
  const isEdit = mode === 'edit' && Boolean(driver)
  const navigate = useNavigate()
  const { notify } = useToast()

  const [values, setValues] = useState<FormValues>(() => initialValues(driver))
  const [photo, setPhoto] = useState<File | null>(null)
  const [documents, setDocuments] = useState<File[]>([])
  const [errors, setErrors] = useState<FormErrors>({})
  const [photoError, setPhotoError] = useState<string | undefined>()
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [codeUnlocked, setCodeUnlocked] = useState(false)
  const [unique, setUnique] = useState({
    codeTaken: false,
    plateTaken: false,
  })
  // Initial payment state
  const [includeInitialPayment, setIncludeInitialPayment] = useState(false)
  const [initialPaymentAmount, setInitialPaymentAmount] = useState('')
  const [initialPaymentPeriodStart, setInitialPaymentPeriodStart] = useState('')
  const initialPaymentPeriodEnd = initialPaymentPeriodStart
    ? jalaliQuarterEnd(initialPaymentPeriodStart)
    : null
  const [initialPaymentDate, setInitialPaymentDate] = useState(todayIsoKabul)
  const [initialPaymentErrors, setInitialPaymentErrors] =
    useState<InitialPaymentErrors>({})
  const [initialPaymentIdempotencyKey, setInitialPaymentIdempotencyKey] = useState<string | null>(null)

  const setValue = (key: keyof FormValues, value: string | boolean) => {
    setValues((current) => ({ ...current, [key]: value }) as FormValues)
  }

  useEffect(() => {
    const code = normalizeDigits(values.driver_code).trim()
    const plate = values.plate_number.trim()

    setUnique({ codeTaken: false, plateTaken: false })
    if (!code && !plate) return

    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      checkDriverUnique(
        {
          driver_code: code || undefined,
          plate_number: plate || undefined,
          exclude: driver?.id,
        },
        controller.signal,
      )
        .then((result) => {
          setUnique({
            codeTaken: Boolean(result.driver_code_taken),
            plateTaken: Boolean(result.plate_number_taken),
          })
        })
        .catch(() => undefined)
    }, 450)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [values.driver_code, values.plate_number, driver?.id])

  useEffect(() => {
    if (includeInitialPayment && !initialPaymentIdempotencyKey) {
      setInitialPaymentIdempotencyKey(crypto.randomUUID())
    }
  }, [includeInitialPayment, initialPaymentIdempotencyKey])

  const fieldError = (field: DriverField): string | undefined => {
    if (field === 'driver_code' && unique.codeTaken) {
      return 'این شماره مسلسل قبلاً برای راننده دیگری ثبت شده است.'
    }
    if (field === 'plate_number' && unique.plateTaken) {
      return 'این پلیت قبلاً برای راننده دیگری ثبت شده است.'
    }
    return errors[field]
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submitting) return

    const clientErrors = validate(values, !isEdit)
    setErrors(clientErrors)
    setFormError(null)

    if (Object.keys(clientErrors).length > 0) {
      notify('error', 'لطفاً خطاهای مشخص‌شده در فرم را برطرف کنید.')
      return
    }

    if (!isEdit && includeInitialPayment) {
      const paymentErrors: InitialPaymentErrors = {}
      const amount = normalizeDigits(initialPaymentAmount).trim()

      if (!/^\d+$/.test(amount)) {
        paymentErrors.amount = 'مبلغ پرداخت باید یک عدد صحیح یا صفر باشد.'
      }
      if (/^\d+$/.test(amount) && Number(amount) > 0) {
        if (!isValidIsoDate(initialPaymentDate)) {
          paymentErrors.date = 'تاریخ پرداخت را از تقویم انتخاب کنید.'
        } else if (initialPaymentDate > todayIsoKabul()) {
          paymentErrors.date = 'تاریخ پرداخت نمی‌تواند در آینده باشد.'
        }
        if (!initialPaymentPeriodStart) {
          paymentErrors.periodStart = 'تاریخ شروع دوره را انتخاب کنید.'
        }
        if (
          initialPaymentPeriodStart &&
          initialPaymentPeriodEnd &&
          !isValidJalaliQuarterPeriod(
            values.fee_start_date,
            initialPaymentPeriodStart,
            initialPaymentPeriodEnd,
          )
        ) {
          paymentErrors.periodStart =
            'این تاریخ شروع با دوره‌های سه‌ماهه شمسی بر اساس تاریخ شروع فیس مطابقت ندارد.'
        }
      }
      setInitialPaymentErrors(paymentErrors)
      if (Object.keys(paymentErrors).length > 0) {
        notify('error', 'اطلاعات پرداخت اولیه را بررسی کنید.')
        return
      }
    }

    if (unique.codeTaken || unique.plateTaken) {
      notify('error', 'شماره مسلسل یا پلیت وارد شده قبلاً ثبت شده است.')
      return
    }

    const initialPaymentRequested =
      !isEdit &&
      includeInitialPayment &&
      Number(normalizeDigits(initialPaymentAmount).trim()) > 0

    setSubmitting(true)
    try {
      // Re-check immediately so a fast submit cannot bypass the debounce.
      try {
        const result = await checkDriverUnique({
          driver_code: normalizeDigits(values.driver_code).trim(),
          plate_number: values.plate_number.trim(),
          exclude: driver?.id,
        })
        if (result.driver_code_taken || result.plate_number_taken) {
          setUnique({
            codeTaken: Boolean(result.driver_code_taken),
            plateTaken: Boolean(result.plate_number_taken),
          })
          notify('error', 'شماره مسلسل یا پلیت وارد شده قبلاً ثبت شده است.')
          return
        }
      } catch {
        // If the pre-check is unavailable, the server still enforces uniqueness.
      }

      const payload: DriverPayload = { ...values, photo }
      if (initialPaymentRequested && initialPaymentPeriodStart) {
        const idempotencyKey =
          initialPaymentIdempotencyKey ?? crypto.randomUUID()
        if (!initialPaymentIdempotencyKey) {
          setInitialPaymentIdempotencyKey(idempotencyKey)
        }
        payload.initial_payment_amount = normalizeDigits(
          initialPaymentAmount,
        ).trim()
        payload.initial_payment_date = initialPaymentDate
        payload.initial_payment_period_start = initialPaymentPeriodStart
        payload.initial_payment_idempotency_key = idempotencyKey
      }

      let saved: any
      if (isEdit) {
        saved = await updateDriver(driver!.id, payload)
      } else {
        saved = await createDriver(payload)
      }

      // Upload documents after driver creation
      let docError: string | null = null
      if (documents.length > 0 && !isEdit) {
        try {
          await uploadDocuments(saved.id, documents)
        } catch (cause) {
          docError = getErrorMessage(cause)
        }
      }

      if (docError) {
        notify('error', `راننده ثبت شد، اما در آپلود اسناد خطایی رخ داد: ${docError}`)
      }
      if (!docError) {
        const completedActions = []
        if (documents.length > 0) {
          completedActions.push(`${documents.length} سند آپلود شد`)
        }
        if (initialPaymentRequested) completedActions.push('پرداخت ثبت شد')
        notify(
          'success',
          isEdit
            ? 'تغییرات راننده با موفقیت ذخیره شد.'
            : `راننده جدید با موفقیت ثبت شد${completedActions.length ? ` و ${completedActions.join(' و ')}` : ''}.`,
        )
      }
      navigate(`/drivers/${saved.id}`, { replace: isEdit })
    } catch (cause) {
      setPhotoError(undefined)
      if (cause instanceof ApiError) {
        const mapped: FormErrors = {}
        const paymentFieldMap: Record<string, keyof InitialPaymentErrors> = {
          initial_payment_amount: 'amount',
          initial_payment_date: 'date',
          initial_payment_period_start: 'periodStart',
        }
        for (const [key, messages] of Object.entries(cause.fieldErrors)) {
          const message = messages?.[0]
          if (!message) continue
          const paymentField = paymentFieldMap[key]
          if (key === 'photo') {
            setPhotoError(message)
          } else if (key === 'non_field_errors' || key === 'detail') {
            setFormError(message)
          } else if (paymentField) {
            setInitialPaymentErrors((current) => ({
              ...current,
              [paymentField]: message,
            }))
          } else {
            mapped[key as DriverField] = message
          }
        }
        setErrors(mapped)
      }
      notify('error', getErrorMessage(cause))
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } finally {
      setSubmitting(false)
    }
  }

  const cancelTo = isEdit ? `/drivers/${driver!.id}` : '/drivers'

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      {formError && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <XCircleIcon className="mt-0.5 size-4 shrink-0" />
          <p>{formError}</p>
        </div>
      )}

      <SectionCard
        title="مشخصات راننده"
        description="شماره مسلسل را به‌صورت دستی وارد کنید. این شماره یکتا است و به‌صورت خودکار تولید نمی‌شود."
      >
        <div className="grid gap-5 md:grid-cols-2">
          <Field
            label="شماره مسلسل"
            htmlFor="driver_code"
            required
            error={fieldError('driver_code')}
            hint={
              isEdit && !codeUnlocked
                ? 'برای جلوگیری از اشتباه، شماره مسلسل قفل شده است.'
                : 'قالب آزاد است؛ مدیر می‌تواند مقدار دلخواه وارد کند.'
            }
          >
            <input
              id="driver_code"
              value={values.driver_code}
              onChange={(event) => setValue('driver_code', event.target.value)}
              disabled={isEdit && !codeUnlocked}
              required
              dir="ltr"
              autoComplete="off"
              placeholder="مثلاً D-00001"
              aria-invalid={Boolean(fieldError('driver_code'))}
              className={cn(inputClass, 'font-mono')}
            />

            {isEdit && (
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                <span className="flex items-center gap-1.5">
                  <LockIcon className="size-3.5" />
                  شماره مسلسل پس از ثبت ثابت می‌ماند.
                </span>
                <button
                  type="button"
                  onClick={() => setCodeUnlocked((current) => !current)}
                  className="inline-flex items-center gap-1 font-medium text-slate-900 underline-offset-2 hover:underline"
                >
                  {codeUnlocked ? (
                    <>
                      <LockIcon className="size-3.5" />
                      قفل مجدد
                    </>
                  ) : (
                    <>
                      <UnlockIcon className="size-3.5" />
                      تغییر شماره مسلسل
                    </>
                  )}
                </button>
              </div>
            )}

            {isEdit && codeUnlocked && (
              <p className="mt-1 flex items-start gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800">
                <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" />
                تغییر شماره مسلسل یک اقدام حساس است و فقط با تأیید مدیر انجام
                شود. شماره قبلی دیگر برای راننده جدید قابل استفاده نخواهد بود.
              </p>
            )}
          </Field>

          <Field
            label="نام کامل"
            htmlFor="full_name"
            required
            error={fieldError('full_name')}
          >
            <input
              id="full_name"
              value={values.full_name}
              onChange={(event) => setValue('full_name', event.target.value)}
              required
              autoComplete="off"
              aria-invalid={Boolean(fieldError('full_name'))}
              className={inputClass}
            />
          </Field>

          <Field
            label="نام پدر"
            htmlFor="father_name"
            required={!isEdit}
            error={fieldError('father_name')}
          >
            <input
              id="father_name"
              value={values.father_name}
              onChange={(event) => setValue('father_name', event.target.value)}
              required={!isEdit}
              autoComplete="off"
              aria-invalid={Boolean(fieldError('father_name'))}
              className={inputClass}
            />
          </Field>

          <Field
            label="شماره تماس"
            htmlFor="phone"
            required={!isEdit}
            error={fieldError('phone')}
            hint="مثال: 0700123456 — متن مجاز است، عددی ذخیره نمی‌شود."
          >
            <input
              id="phone"
              value={values.phone}
              onChange={(event) => setValue('phone', event.target.value)}
              required={!isEdit}
              dir="ltr"
              inputMode="tel"
              autoComplete="off"
              aria-invalid={Boolean(fieldError('phone'))}
              className={inputClass}
            />
          </Field>

          <Field
            label="شماره تذکره"
            htmlFor="tazkira_number"
            required={!isEdit}
            error={fieldError('tazkira_number')}
          >
            <input
              id="tazkira_number"
              value={values.tazkira_number}
              onChange={(event) =>
                setValue('tazkira_number', event.target.value)
              }
              required={!isEdit}
              dir="ltr"
              autoComplete="off"
              aria-invalid={Boolean(fieldError('tazkira_number'))}
              className={inputClass}
            />
          </Field>

          <Field
            label="پلیت موتر"
            htmlFor="plate_number"
            required
            error={fieldError('plate_number')}
            hint="پلیت باید یکتا باشد. حروف کوچک و بزرگ و فاصله‌های اضافی یکسان‌سازی می‌شوند."
          >
            <input
              id="plate_number"
              value={values.plate_number}
              onChange={(event) => setValue('plate_number', event.target.value)}
              required
              dir="ltr"
              autoComplete="off"
              aria-invalid={Boolean(fieldError('plate_number'))}
              className={cn(inputClass, 'font-mono uppercase')}
            />
          </Field>

          <Field
            label="آدرس"
            htmlFor="address"
            error={fieldError('address')}
            className="md:col-span-2"
          >
            <textarea
              id="address"
              value={values.address ?? ''}
              onChange={(event) => setValue('address', event.target.value)}
              rows={3}
              aria-invalid={Boolean(fieldError('address'))}
              className={textareaClass}
            />
          </Field>
        </div>
      </SectionCard>

      <SectionCard
        title="تاریخ‌ها"
        description="تاریخ را می‌توانید از تقویم شمسی یا میلادی انتخاب کنید. هر دو معادل کنار فیلد نمایش داده می‌شود و مقدار میلادی در دیتابیس ذخیره می‌شود."
      >
        <div className="grid gap-5 md:grid-cols-2">
          <DualDateInput
            id="registration_date"
            label="تاریخ ثبت"
            value={values.registration_date}
            onChange={(iso) => setValue('registration_date', iso)}
            error={fieldError('registration_date')}
          />
          <DualDateInput
            id="fee_start_date"
            label="تاریخ شروع فیس"
            value={values.fee_start_date}
            onChange={(iso) => setValue('fee_start_date', iso)}
            error={fieldError('fee_start_date')}
          />
        </div>
      </SectionCard>

      {!isEdit && (
        <div className="space-y-4">
          {/* کارت فشرده پرداخت اولیه: عنوان + چکباکس در یک ردیف */}
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <label
              htmlFor="include_initial_payment"
              className="flex cursor-pointer items-center gap-2.5"
            >
              <input
                id="include_initial_payment"
                type="checkbox"
                checked={includeInitialPayment}
                onChange={(event) => {
                  setIncludeInitialPayment(event.target.checked)
                  if (!event.target.checked) setInitialPaymentErrors({})
                }}
                className="size-4 rounded border-slate-300 text-brand-600 focus:ring-2 focus:ring-brand-500/30"
              />
              <span className="text-sm font-semibold text-slate-800">
                پرداخت اولیه
              </span>
            </label>

            {includeInitialPayment && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field
                  label="مبلغ پرداخت اولیه (افغانی)"
                  htmlFor="initial_payment_amount"
                  required
                  error={initialPaymentErrors.amount}
                >
                  <input
                    id="initial_payment_amount"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9۰-۹٠-٩]*"
                    className={cn(inputClass, 'font-mono dir-ltr')}
                    value={initialPaymentAmount}
                    onChange={(event) => {
                      setInitialPaymentAmount(event.target.value)
                      setInitialPaymentErrors((current) => ({
                        ...current,
                        amount: undefined,
                      }))
                    }}
                    placeholder="مثلاً ۶۰۰"
                    aria-invalid={Boolean(initialPaymentErrors.amount)}
                  />
                </Field>

                <DualDateInput
                  id="initial_payment_date"
                  label="تاریخ پرداخت"
                  value={initialPaymentDate}
                  onChange={(value) => {
                    setInitialPaymentDate(value)
                    setInitialPaymentErrors((current) => ({
                      ...current,
                      date: undefined,
                    }))
                  }}
                  allowGregorian
                  compact
                  required
                  error={initialPaymentErrors.date}
                />
              </div>
            )}
          </section>

          {/* کارت مستقل: دوره پرداخت + اطلاعات و محاسبات دوره */}
          {includeInitialPayment && (
            <SectionCard title="دوره پرداخت">
              <div className="grid gap-4 md:grid-cols-2">
                <DualDateInput
                  id="initial_payment_period_start"
                  label="تاریخ شروع دوره"
                  value={initialPaymentPeriodStart}
                  onChange={(start) => {
                    setInitialPaymentPeriodStart(start)
                    setInitialPaymentErrors((current) => ({
                      ...current,
                      periodStart: undefined,
                    }))
                  }}
                  required
                  error={initialPaymentErrors.periodStart}
                  hint="شروع باید با دوره‌های سه‌ماهه بر اساس تاریخ شروع فیس منطبق باشد."
                />

                <Field
                  label="تاریخ پایان دوره"
                  htmlFor="initial_payment_period_end"
                  hint="این مقدار فقط‌خواندنی است و خودکار محاسبه می‌شود."
                >
                  <input
                    id="initial_payment_period_end"
                    readOnly
                    aria-readonly="true"
                    value={
                      initialPaymentPeriodEnd
                        ? formatJalaliLong(initialPaymentPeriodEnd)
                        : ''
                    }
                    placeholder="پس از انتخاب تاریخ شروع محاسبه می‌شود"
                    className={cn(inputClass, 'bg-slate-50 text-slate-600')}
                  />
                </Field>
              </div>

              {/* قسمت سوم: اطلاعات و محاسبات دوره */}
              <div className="mt-5 space-y-3 border-t border-slate-100 pt-5">
                <h3 className="text-sm font-semibold text-slate-800">
                  اطلاعات و محاسبات دوره
                </h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-100">
                    <span className="text-slate-400">شمسی: </span>
                    <span className="font-medium">
                      {initialPaymentPeriodEnd
                        ? formatJalaliLong(initialPaymentPeriodEnd)
                        : '—'}
                    </span>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-100">
                    <span className="text-slate-400">میلادی: </span>
                    <span className="font-medium" dir="ltr">
                      {initialPaymentPeriodEnd
                        ? formatGregorianShort(initialPaymentPeriodEnd)
                        : '—'}
                    </span>
                  </div>
                </div>
                <p className="rounded-lg bg-brand-50 px-3 py-2 text-xs font-medium text-brand-700">
                  مدت دوره: سه ماه
                </p>
              </div>
            </SectionCard>
          )}
        </div>
      )}

      <SectionCard
        title="عکس و وضعیت"
        description="عکس به‌عنوان سند راننده در سامانه بارگذاری می‌شود."
      >
        <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
          <PhotoUpload
            file={photo}
            existingUrl={driver?.photo_url}
            onChange={setPhoto}
            error={photoError}
            disabled={submitting}
          />

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-slate-700">
              وضعیت راننده
            </span>
            <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
              <button
                type="button"
                onClick={() => setValue('status', true)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition',
                  values.status
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-500 hover:text-slate-700',
                )}
              >
                <CheckCircleIcon className="size-3.5" />
                فعال
              </button>
              <button
                type="button"
                onClick={() => setValue('status', false)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition',
                  !values.status
                    ? 'bg-slate-600 text-white shadow-sm'
                    : 'text-slate-500 hover:text-slate-700',
                )}
              >
                <XCircleIcon className="size-3.5" />
                غیرفعال
              </button>
            </div>
            <p className="max-w-xs text-xs leading-5 text-slate-500">
              راننده هرگز به‌صورت دائمی حذف نمی‌شود؛ برای پایان همکاری، فقط
              غیرفعال کنید.
            </p>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="اسناد pilotes (PDF)"
        description="یک یا چند PDF یا تصویر JPG، PNG یا WebP (حداکثر ۱۰ مگابایت هر فایل) آپلود کنید. اسناد فقط از طریق API احراز هویت‌شده قابل دسترسی هستند."
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-start gap-3">
            <input
              id="documents"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp"
              multiple
              onChange={(event) => {
                const files = event.target.files
                if (files) {
                  setDocuments(Array.from(files))
                }
              }}
              disabled={submitting}
              className="hidden"
            />
            <label
              htmlFor="documents"
              className={`flex flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-6 transition cursor-pointer ${submitting ? 'opacity-60 pointer-events-none' : ''}`}
              onMouseEnter={() => {}}
              onMouseLeave={() => {}}
              style={{
                borderColor: submitting ? '#cbd5e1' : '#94a3b8',
                backgroundColor: submitting ? '#f1f5f9' : '#f8fafc',
              }}
            >
              <CloudUploadIcon className="size-6 text-slate-400" />
              <p className="text-sm font-medium text-slate-600">
                {documents.length > 0
                  ? `${documents.length} فایل انتخاب شده`
                  : 'انتخاب PDF یا تصویر'}
              </p>
              <p className="text-xs text-slate-500">
                PDF یا JPG، PNG و WebP — حداکثر ۱۰ مگابایت هر فایل
              </p>
            </label>
          </div>

          {documents.length > 0 && (
            <div className="space-y-2">
              {documents.map((file, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-700 truncate">
                      {file.name}
                    </div>
                    <div className="text-xs text-slate-500">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      setDocuments(documents.filter((_, i) => i !== idx))
                    }
                    className="text-rose-500 hover:text-rose-700"
                  >
                    <XIcon className="size-4" />
                  </button>
                </div>
              ))}
            </div>
          )}

        </div>
      </SectionCard>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Link
          to={cancelTo}
          className="inline-flex h-10 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
        >
          انصراف
        </Link>
        <Button
          type="submit"
          loading={submitting}
          icon={<CheckIcon className="size-4" />}
        >
          {submitting
            ? 'در حال ذخیره…'
            : isEdit
              ? 'ذخیره تغییرات'
              : 'ثبت راننده'}
        </Button>
      </div>
    </form>
  )
}
