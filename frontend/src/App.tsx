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
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { FinancialDashboardPage } from './pages/FinancialDashboardPage'
import { DriverFinancialPage } from './pages/DriverFinancialPage'
import { PaymentRegisterPage } from './pages/PaymentRegisterPage'
import { PaymentVoidPage } from './pages/PaymentVoidPage'
import { PaymentCorrectPage } from './pages/PaymentCorrectPage'
import { AllocationCorrectPage } from './pages/AllocationCorrectPage'
import { AllocationCorrectCreditPage } from './pages/AllocationCorrectCreditPage'
import { FinancialHistoryPage } from './pages/FinancialHistoryPage'
import { CashRevenueReportPage } from './pages/CashRevenueReportPage'
import { FinancialReportPage } from './pages/FinancialReportPage'
import { UserManagementPage } from './pages/UserManagementPage'

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
                <Route path="drivers/new" element={<DriverCreatePage />} />
                <Route path="drivers/:id" element={<DriverProfilePage />} />
                <Route path="drivers/:id/edit" element={<DriverEditPage />} />
                <Route path="financial" element={<FinancialDashboardPage />} />
                <Route path="financial/drivers/:id" element={<DriverFinancialPage />} />
                <Route path="financial/payments/new" element={<PaymentRegisterPage />} />
                <Route path="financial/payments/:id/void" element={<PaymentVoidPage />} />
                <Route path="financial/payments/:id/correct" element={<PaymentCorrectPage />} />
                <Route path="financial/allocations/:id/correct" element={<AllocationCorrectPage />} />
                <Route path="financial/allocations/:id/correct-credit" element={<AllocationCorrectCreditPage />} />
                <Route path="financial/history" element={<FinancialHistoryPage />} />
                <Route path="financial/reports/cash-revenue" element={<CashRevenueReportPage />} />
                <Route path="financial/reports/financial" element={<FinancialReportPage />} />
                <Route path="users" element={<UserManagementPage />} />
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
