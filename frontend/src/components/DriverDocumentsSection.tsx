import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { AlertCircleIcon, EyeIcon, RefreshIcon, XIcon } from './icons'
import { Button } from './ui/Button'
import { Spinner } from './ui/Spinner'
import { useToast } from '../context/ToastContext'
import {
  ApiError,
  downloadDocument,
  fetchDriverDocuments,
  uploadDocuments,
} from '../lib/api'
import { formatKabulDateTime } from '../lib/dates'
import { getErrorMessage, isAbortError } from '../lib/errors'
import type { DocumentUploadItem } from '../lib/api'

const MAX_FILE_SIZE = 10 * 1024 * 1024

function getDocumentErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return 'نشست ورود منقضی شده است؛ دوباره وارد سیستم شوید.'
  }
  if (error instanceof TypeError) {
    return 'ارتباط با سرور برقرار نشد؛ اتصال را بررسی و دوباره تلاش کنید.'
  }
  return getErrorMessage(error)
}

interface DriverDocumentsSectionProps {
  driverId: number
  canManage: boolean
}

export function DriverDocumentsSection({
  driverId,
  canManage,
}: DriverDocumentsSectionProps) {
  const { notify } = useToast()
  const [documents, setDocuments] = useState<DocumentUploadItem[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [previewingId, setPreviewingId] = useState<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [preview, setPreview] = useState<{
    url: string
    contentType: string
    name: string
  } | null>(null)

  useEffect(() => {
    let active = true
    const controller = new AbortController()

    fetchDriverDocuments(driverId, controller.signal)
      .then((items) => {
        if (active) setDocuments(items)
      })
      .catch((cause) => {
        if (active && !isAbortError(cause)) {
          setListError(getDocumentErrorMessage(cause))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [driverId, refreshKey])

  const reloadDocuments = () => {
    setLoading(true)
    setListError(null)
    setRefreshKey((current) => current + 1)
  }

  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview.url)
    },
    [preview],
  )

  const handleFilesChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    const oversizedFile = files.find((file) => file.size > MAX_FILE_SIZE)
    if (oversizedFile) {
      setSelectedFiles([])
      setUploadError(`حجم «${oversizedFile.name}» بیش از ۱۰ مگابایت است.`)
      event.target.value = ''
      return
    }
    setSelectedFiles(files)
    setUploadError(null)
  }

  const handleUpload = async () => {
    if (!canManage || !selectedFiles.length || uploading) return
    setUploading(true)
    setUploadError(null)
    try {
      await uploadDocuments(driverId, selectedFiles)
      setSelectedFiles([])
      if (fileInputRef.current) fileInputRef.current.value = ''
      reloadDocuments()
      notify('success', 'اسناد راننده با موفقیت بارگذاری شد.')
    } catch (cause) {
      setUploadError(getDocumentErrorMessage(cause))
    } finally {
      setUploading(false)
    }
  }

  const handleDownload = async (item: DocumentUploadItem) => {
    try {
      const blob = await downloadDocument(item.id)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = item.original_filename || item.document_name
      anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) {
      notify('error', getDocumentErrorMessage(cause))
    }
  }

  const handlePreview = async (item: DocumentUploadItem) => {
    setPreviewingId(item.id)
    setPreviewError(null)
    try {
      const blob = await downloadDocument(item.id)
      setPreview({
        url: URL.createObjectURL(blob),
        contentType: blob.type || item.content_type,
        name: item.original_filename || item.document_name,
      })
    } catch (cause) {
      notify('error', getDocumentErrorMessage(cause))
    } finally {
      setPreviewingId(null)
    }
  }

  return (
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">اسناد راننده</h2>
          <p className="mt-0.5 text-xs leading-5 text-slate-500">
            فایل‌ها فقط از طریق دسترسی احراز هویت‌شده قابل مشاهده و دریافت هستند.
          </p>
        </div>
        {canManage && (
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50">
            <input
              ref={fileInputRef}
              className="sr-only"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp"
              multiple
              onChange={handleFilesChange}
              disabled={uploading}
            />
            انتخاب سند
          </label>
        )}
      </div>

      {canManage && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <p className="min-w-0 flex-1 text-xs text-slate-500">
            {selectedFiles.length
              ? selectedFiles.map((file) => file.name).join('، ')
              : 'PDF یا تصویر JPG، PNG و WebP؛ حداکثر ۱۰ مگابایت برای هر فایل'}
          </p>
          <Button
            size="sm"
            loading={uploading}
            disabled={!selectedFiles.length}
            onClick={handleUpload}
          >
            بارگذاری
          </Button>
        </div>
      )}

      {uploadError && (
        <p className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {uploadError}
        </p>
      )}

      {loading && documents.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
          <Spinner className="size-5" />
          در حال دریافت اسناد…
        </div>
      ) : null}

      {listError && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          <span className="flex items-center gap-2">
            <AlertCircleIcon className="size-4 shrink-0" />
            {listError}
          </span>
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshIcon className="size-4" />}
            onClick={reloadDocuments}
          >
            تلاش دوباره
          </Button>
        </div>
      )}

      {loading && documents.length > 0 && (
        <p className="mt-3 text-xs text-slate-500">در حال به‌روزرسانی فهرست اسناد…</p>
      )}

      {!loading && !listError && documents.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">
          هنوز سندی ثبت نشده است
        </p>
      ) : null}

      {documents.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100">
          {documents.map((item) => {
            const fileType =
              item.content_type === 'application/pdf'
                ? 'PDF'
                : item.content_type.includes('/')
                  ? item.content_type.split('/')[1]?.toUpperCase() || 'فایل'
                  : 'فایل'
            return (
              <li
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-1"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800">
                    {item.document_name || item.original_filename}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {fileType} · {formatKabulDateTime(item.upload_date)} ·{' '}
                    {item.file_size_mb} MB ·{' '}
                    {item.status === 'active' ? 'فعال' : 'غیرفعال'}
                  </p>
                  {item.description && (
                    <p className="mt-1 text-xs text-slate-600">
                      {item.description}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={previewingId === item.id}
                    icon={<EyeIcon className="size-4" />}
                    onClick={() => handlePreview(item)}
                  >
                    مشاهده
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDownload(item)}
                  >
                    دانلود
                  </Button>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
          role="dialog"
          aria-modal="true"
          aria-label={`پیش‌نمایش ${preview.name}`}
        >
          <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-slate-900/5">
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
              <h3 className="truncate text-sm font-semibold text-slate-800">
                {preview.name}
              </h3>
              <Button
                variant="ghost"
                size="sm"
                icon={<XIcon className="size-4" />}
                onClick={() => setPreview(null)}
                aria-label="بستن پیش‌نمایش"
              />
            </div>
            <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-slate-100 p-3">
              {previewError ? (
                <p className="text-sm text-rose-700">{previewError}</p>
              ) : preview.contentType === 'application/pdf' ? (
                <iframe
                  src={preview.url}
                  title={preview.name}
                  className="h-[75vh] w-full rounded border border-slate-200 bg-white"
                  onError={() =>
                    setPreviewError('پیش‌نمایش PDF بارگذاری نشد؛ فایل را دانلود کنید.')
                  }
                />
              ) : preview.contentType.startsWith('image/') ? (
                <img
                  src={preview.url}
                  alt={preview.name}
                  className="max-h-[75vh] max-w-full object-contain"
                  onError={() =>
                    setPreviewError('پیش‌نمایش تصویر بارگذاری نشد؛ فایل را دانلود کنید.')
                  }
                />
              ) : (
                <p className="text-sm text-slate-600">
                  پیش‌نمایش این نوع فایل در مرورگر پشتیبانی نمی‌شود.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
