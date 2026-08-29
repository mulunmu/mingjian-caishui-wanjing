import { Crown, X } from 'lucide-react';

interface UpgradeModalProps {
  open: boolean;
  onClose: () => void;
  feature?: string;
}

/** 定制功能升级提示弹窗：非定制用户点击定制功能时弹出。 */
export default function UpgradeModal({ open, onClose, feature = '该功能' }: UpgradeModalProps) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-warm-900/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-[400px] max-w-[92vw] rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded text-warm-400 hover:bg-warm-100 transition-colors"
          title="关闭"
        >
          <X size={16} />
        </button>

        <div className="mb-3 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100">
            <Crown className="h-5 w-5 text-amber-500" />
          </div>
          <h3 className="text-base font-semibold text-warm-800">定制用户专享</h3>
        </div>

        <p className="mb-1 text-sm leading-relaxed text-warm-600">
          {feature}为<strong className="text-warm-800">定制用户</strong>专享功能。
        </p>
        <p className="mb-5 text-xs leading-relaxed text-warm-400">
          当前账号为非定制用户，可预览报告，但无法生成 / 下载。升级后解锁全部报告分析、主动监测与场景定制。
        </p>
        <p className="mb-5 text-xs leading-relaxed text-warm-500">
          如需开通定制权限，请联系您的服务顾问或管理员。
        </p>

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="h-9 rounded-lg border border-warm-200 px-4 text-sm text-warm-600 transition-colors hover:bg-warm-50"
          >
            我知道了
          </button>
        </div>
      </div>
    </div>
  );
}
