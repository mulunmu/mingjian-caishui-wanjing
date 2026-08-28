import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect } from 'react';
import Header from './components/layout/Header';
import ResearchCenter from './pages/ResearchCenter';
import ReportPage from './pages/ReportPage';
import OverviewPage from './pages/OverviewPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ReportCenter from './pages/ReportCenter';
import FraudPage from './pages/FraudPage';
import AuthenticityPage from './pages/AuthenticityPage';
import EnterprisePage from './pages/EnterprisePage';
import DataIngestPage from './pages/DataIngestPage';
import useAuthStore from './stores/authStore';

// 受保护的路由包装器
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoggedIn } = useAuthStore();

  if (!isLoggedIn) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  const location = useLocation();
  const { isLoggedIn, checkAuth } = useAuthStore();
  const isAuthPage = location.pathname === '/login' || location.pathname === '/register';

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

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
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
