import { Link } from 'react-router-dom'
import { DriverForm } from '../components/DriverForm'
import { ArrowRightIcon } from '../components/icons'
import { PageHeader } from '../components/ui/PageHeader'

export function DriverCreatePage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="ثبت راننده جدید"
        description="اطلاعات راننده را کامل وارد کنید. شماره مسلسل الزامی، دستی و یکتاست و تاریخ‌ها به هر دو تقویم نمایش داده می‌شوند."
        actions={
          <Link
            to="/drivers"
            className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
          >
            <ArrowRightIcon className="size-4" />
            بازگشت به فهرست
          </Link>
        }
      />
      <DriverForm mode="create" />
    </div>
  )
}
