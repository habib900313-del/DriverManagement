import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AuthProvider } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import { DashboardPage } from './pages/DashboardPage'
import { DriverCreatePage } from './pages/DriverCreatePage'
import { DriverEditPage } from './pages/DriverEditPage'
import { DriverProfilePage } from './pages/DriverProfilePage'
import { DriversListPage } from './pages/DriversListPage'
import { ArchivedDriversPage } from './pages/ArchivedDriversPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { FinancialDashboardPage } from './pages/FinancialDashboardPage'
import { DriverFinancialPage } from './pages/DriverFinancialPage'
import { PaymentRegisterPage } from './pages/PaymentRegisterPage'
import { PaymentVoidPage } from './pages/PaymentVoidPage'
import { PaymentCorrectPage } from './pages/PaymentCorrectPage'
import { PaymentDetailPage } from './pages/PaymentDetailPage'
import { PaymentRefundPage } from './pages/PaymentRefundPage'
import { AllocationCorrectPage } from './pages/AllocationCorrectPage'
import { AllocationCorrectCreditPage } from './pages/AllocationCorrectCreditPage'
import { FinancialHistoryPage } from './pages/FinancialHistoryPage'
import { CashRevenueReportPage } from './pages/CashRevenueReportPage'
import { FinancialReportPage } from './pages/FinancialReportPage'
import { UserManagementPage } from './pages/UserManagementPage'
import { ActivityLogsPage } from './pages/ActivityLogsPage'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route index element={<DashboardPage />} />
                <Route path="drivers" element={<DriversListPage />} />
                <Route element={<ProtectedRoute requiredRole="manager" />}>
                  <Route path="drivers/archived" element={<ArchivedDriversPage />} />
                </Route>
                <Route path="drivers/:id" element={<DriverProfilePage />} />
                <Route path="financial" element={<FinancialDashboardPage />} />
                <Route path="financial/drivers/:id" element={<DriverFinancialPage />} />
                <Route path="financial/payments/:id" element={<PaymentDetailPage />} />
                <Route path="financial/history" element={<FinancialHistoryPage />} />
                <Route path="financial/reports/cash-revenue" element={<CashRevenueReportPage />} />
                <Route path="financial/reports/financial" element={<FinancialReportPage />} />
                <Route element={<ProtectedRoute requiredRole="manager" />}>
                  <Route path="drivers/new" element={<DriverCreatePage />} />
                  <Route path="drivers/:id/edit" element={<DriverEditPage />} />
                  <Route path="financial/payments/new" element={<PaymentRegisterPage />} />
                  <Route path="financial/payments/:id/void" element={<PaymentVoidPage />} />
                  <Route path="financial/payments/:id/correct" element={<PaymentCorrectPage />} />
                  <Route path="financial/payments/:id/refund" element={<PaymentRefundPage />} />
                  <Route path="financial/allocations/:id/correct" element={<AllocationCorrectPage />} />
                  <Route path="financial/allocations/:id/correct-credit" element={<AllocationCorrectCreditPage />} />
                </Route>
                <Route element={<ProtectedRoute requiredRole="superuser" />}>
                  <Route path="users" element={<UserManagementPage />} />
                  <Route path="admin/activity-logs" element={<ActivityLogsPage />} />
                </Route>
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Route>
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
