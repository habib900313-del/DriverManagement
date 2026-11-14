import { ArrowRightIcon, SearchIcon } from '../components/icons'
import { LinkButton } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'

export function NotFoundPage() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <EmptyState
        icon={<SearchIcon className="size-6" />}
        title="صفحه مورد نظر یافت نشد"
        description="نشانی وارد شده معتبر نیست یا این صفحه حذف شده است."
        action={
          <LinkButton
            to="/"
            variant="secondary"
            size="sm"
            icon={<ArrowRightIcon className="size-4" />}
          >
            بازگشت به داشبورد
          </LinkButton>
        }
      />
    </div>
  )
}
