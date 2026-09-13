import { NavLink, useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { CuteEyeLogo } from '@/components/ui/CuteEyeLogo';
import useAuthStore from '@/stores/authStore';
import useOverviewStore from '@/stores/overviewStore';

/** 演示/业务叙事：先接入数据，再监测与研判、出报告 */
const navItems = [
  { path: '/ingest', label: '数据接入' },
  { path: '/overview', label: '风险态势' },
  { path: '/', label: '风险评估' },
  { path: '/report', label: '报告中心' },
  { path: '/emails', label: '发送记录' },
  { path: '/risk/fraud', label: '反欺诈' },
  { path: '/risk/authenticity', label: '真实性' },
];

export default function Header() {
  const navigate = useNavigate();
  const { isLoggedIn, user, logout } = useAuthStore();
  const sampleCount = useOverviewStore((s) => s.kpi?.sample_count);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="h-14 bg-white border-b border-warm-200 flex items-center px-6 flex-shrink-0 z-50">
      {/* Logo → 风险态势 */}
      <button
        type="button"
        onClick={() => navigate('/overview')}
        className="flex items-center gap-3 mr-8 hover:opacity-90 transition-opacity"
        title="回到风险态势"
      >
        <CuteEyeLogo size={36} />
        <span className="text-xl font-bold text-warm-800 tracking-tight">
          明鉴・财税票・万景
        </span>
      </button>

      {/* 导航 */}
      <nav className="flex items-center gap-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              `px-3 py-1.5 text-sm rounded-md transition-colors duration-150 ${
                isActive
                  ? 'text-amber font-medium bg-amber/5'
                  : 'text-warm-500 hover:text-warm-700 hover:bg-warm-100'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* 右侧信息 */}
      <div className="ml-auto flex items-center gap-4">
        <span className="text-xs text-warm-400">
          {typeof sampleCount === 'number' ? `数据样本 ${sampleCount} 家` : '数据样本 …'}
        </span>
        {isLoggedIn && (
          <div className="flex items-center gap-3">
            <NavLink
              to="/account"
              className="text-xs text-warm-500 hover:text-amber transition-colors"
              title="账号与受信邮箱管理"
            >
              {user?.email || ''}
            </NavLink>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1 text-xs text-warm-400 hover:text-warm-600 transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
              退出
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
