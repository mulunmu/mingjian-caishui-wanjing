import { Routes, Route, useLocation, Navigate, Link, useSearchParams } from 'react-router-dom';
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
import EmailLogsPage from './pages/EmailLogsPage';
import AccountPage from './pages/AccountPage';
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
      <Link to="/" className="mt-4 text-amber hover:underline text-sm">
        返回风险研判
      </Link>
    </div>
  );
}

// 兼容旧 /report 深链以外的别名：保留 query
function ReportAliasRedirect() {
  const [sp] = useSearchParams();
  const q = sp.toString();
  return <Navigate to={q ? `/report?${q}` : '/report'} replace />;
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
              {/* 默认落地：风险研判（演示主线） */}
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <ResearchCenter />
                  </ProtectedRoute>
                }
              />
              {/* 出报告 */}
              <Route
                path="/report"
                element={
                  <ProtectedRoute>
                    <ReportCenter />
                  </ProtectedRoute>
                }
              />
              {/* 兼容旧别名：保留 query 转到报告中心 */}
              <Route path="/reports" element={<ReportAliasRedirect />} />
              {/* 风险研判（对话）— 与 / 同页，便于深链 */}
              <Route
                path="/research"
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
                    <Navigate to="/?ingest=1" replace />
                  </ProtectedRoute>
                }
              />
              {/* 兼容旧链接已由上方 /report 承接；报告详情 */}
              <Route
                path="/report/:id"
                element={
                  <ProtectedRoute>
                    <ReportPage />
                  </ProtectedRoute>
                }
              />
              {/* 反欺诈/真实性：保留深链，不再一级导航 */}
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
                path="/emails"
                element={
                  <ProtectedRoute>
                    <EmailLogsPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/account"
                element={
                  <ProtectedRoute>
                    <AccountPage />
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
