import { useEffect, useRef, useState, type ReactNode } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { ChevronDown, LogOut, Mail, Shield, UserRound, LayoutDashboard, Fingerprint } from 'lucide-react';
import { CuteEyeLogo } from '@/components/ui/CuteEyeLogo';
import useAuthStore from '@/stores/authStore';
import useOverviewStore from '@/stores/overviewStore';

/** 主线入口：风险研判 / 出报告（数据接入并入研判弹窗） */
const navItems = [
  { path: '/', label: '风险研判', end: true },
  { path: '/report', label: '出报告', end: false },
];

export default function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isLoggedIn, user, logout } = useAuthStore();
  const sampleCount = useOverviewStore((s) => s.kpi?.sample_count);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [menuOpen]);

  const handleLogout = () => {
    setMenuOpen(false);
    logout();
    navigate('/login');
  };

  return (
    <header className="h-14 bg-white border-b border-warm-200 flex items-center px-6 flex-shrink-0 z-50">
      {/* Logo → 风险研判（主线落地） */}
      <button
        type="button"
        onClick={() => navigate('/')}
        className="flex items-center gap-3 mr-8 hover:opacity-90 transition-opacity"
        title="风险研判"
      >
        <CuteEyeLogo size={36} />
        <span className="text-xl font-bold text-warm-800 tracking-tight">
          明鉴・财税票・万景
        </span>
      </button>

      {/* 主线导航：仅 3 项 */}
      <nav className="flex items-center gap-1" aria-label="主线导航">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            className={({ isActive }) => {
              const researchActive =
                item.path === '/' &&
                (location.pathname === '/' || location.pathname === '/research');
              const active = item.path === '/' ? researchActive : isActive;
              return `px-3 py-1.5 text-sm rounded-md transition-colors duration-150 ${
                active
                  ? 'text-amber font-medium bg-amber/5'
                  : 'text-warm-500 hover:text-warm-700 hover:bg-warm-100'
              }`;
            }}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* 右侧：样本数 + 用户菜单（发送记录 / 账号 / 次级页） */}
      <div className="ml-auto flex items-center gap-4">
        <span className="text-xs text-warm-400">
          {typeof sampleCount === 'number' ? `数据样本 ${sampleCount} 家` : '数据样本 …'}
        </span>
        {isLoggedIn && (
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-warm-600 hover:text-warm-800 px-2 py-1.5 rounded-md hover:bg-warm-100 transition-colors"
              title="账号与更多"
            >
              <UserRound className="w-3.5 h-3.5" />
              <span className="max-w-[140px] truncate">{user?.email || '账号'}</span>
              <ChevronDown
                className={`w-3 h-3 text-warm-400 transition-transform ${menuOpen ? 'rotate-180' : ''}`}
              />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 z-30 w-52 rounded-lg border border-warm-200 bg-white shadow-warm-md py-1">
                <MenuLink
                  to="/account"
                  icon={<UserRound className="w-3.5 h-3.5" />}
                  label="账号与受信邮箱"
                  onClick={() => setMenuOpen(false)}
                />
                <MenuLink
                  to="/emails"
                  icon={<Mail className="w-3.5 h-3.5" />}
                  label="发送记录"
                  onClick={() => setMenuOpen(false)}
                />
                <MenuLink
                  to="/overview"
                  icon={<LayoutDashboard className="w-3.5 h-3.5" />}
                  label="风险态势"
                  onClick={() => setMenuOpen(false)}
                />
                <div className="my-1 border-t border-warm-100" />
                <p className="px-3 pt-1 pb-0.5 text-[10px] text-warm-400">引擎能力（报告章节）</p>
                <MenuLink
                  to="/risk/fraud"
                  icon={<Shield className="w-3.5 h-3.5" />}
                  label="反欺诈"
                  onClick={() => setMenuOpen(false)}
                />
                <MenuLink
                  to="/risk/authenticity"
                  icon={<Fingerprint className="w-3.5 h-3.5" />}
                  label="真实性"
                  onClick={() => setMenuOpen(false)}
                />
                <div className="my-1 border-t border-warm-100" />
                <button
                  type="button"
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-warm-500 hover:bg-warm-50 hover:text-warm-700 transition-colors"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  退出登录
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

function MenuLink({
  to,
  icon,
  label,
  onClick,
}: {
  to: string;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center gap-2 px-3 py-2 text-xs transition-colors ${
          isActive ? 'text-amber bg-amber/5' : 'text-warm-600 hover:bg-warm-50 hover:text-warm-800'
        }`
      }
    >
      {icon}
      {label}
    </NavLink>
  );
}
