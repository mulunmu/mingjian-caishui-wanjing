import { Routes, Route, useLocation, Navigate, Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect } from 'react';
import Header from './components/layout/Header';
import Footer from './components/layout/Footer';
import ResearchCenter from './pages/ResearchCenter';
import ReportPage from './pages/ReportPage';
import OverviewPage from './pages/OverviewPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ReportCenter from './pages/ReportCenter';
import FraudPage from './pages/FraudPage';
import AuthenticityPage from './pages/AuthenticityPage';
import EnterprisePage from './pages/EnterprisePage';
import DataIngestPage from './pages/DataIngestPage';
import useAuthStore from './stores/authStore';
import useOverviewStore from './stores/overviewStore';

// 受保护的路由包装器
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoggedIn } = useAuthStore();

  if (!isLoggedIn) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

// 404 兜底：未匹配路由给出明确反馈，不白屏
function NotFound() {
  return (
    <div className="h-full flex flex-col items-center justify-center p-6 text-center">
      <p className="text-4xl font-bold text-warm-300">404</p>
      <p className="text-warm-500 mt-2 text-sm">页面不存在或已移动</p>
      <Link to="/overview" className="mt-4 text-amber hover:underline text-sm">
        返回风险态势
      </Link>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  const { isLoggedIn, checkAuth } = useAuthStore();
  const kpi = useOverviewStore((s) => s.kpi);
  const fetchOverview = useOverviewStore((s) => s.fetchOverview);
  const isAuthPage =
    location.pathname === '/login' ||
    location.pathname === '/register' ||
    location.pathname === '/forgot-password';
  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // 登录后全局拉取一次总览，供 Header/Footer 显示「数据样本 N 家」。
  // 后续由 DataIngestPage 在导入成功后触发 fetchOverview 同步（见 #55）。
  useEffect(() => {
    if (isLoggedIn && !kpi) {
      void fetchOverview();
    }
  }, [isLoggedIn, kpi, fetchOverview]);

  return (
    <div className="flex flex-col h-full bg-warm-50">
      {!isAuthPage && isLoggedIn && <Header />}
      <main className={isAuthPage ? '' : 'flex-1 overflow-hidden'}>
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            className="h-full"
          >
            <Routes location={location}>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <ResearchCenter />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/overview"
                element={
                  <ProtectedRoute>
                    <OverviewPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/ingest"
                element={
                  <ProtectedRoute>
                    <DataIngestPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/report"
                element={
                  <ProtectedRoute>
                    <ReportCenter />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/report/:id"
                element={
                  <ProtectedRoute>
                    <ReportPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/risk/fraud"
                element={
                  <ProtectedRoute>
                    <FraudPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/risk/authenticity"
                element={
                  <ProtectedRoute>
                    <AuthenticityPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/enterprise/:id"
                element={
                  <ProtectedRoute>
                    <EnterprisePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="*"
                element={
                  <ProtectedRoute>
                    <NotFound />
                  </ProtectedRoute>
                }
              />
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>
      {!isAuthPage && isLoggedIn && <Footer />}
    </div>
  );
}
