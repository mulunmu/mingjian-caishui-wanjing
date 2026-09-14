import { X } from 'lucide-react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  /** 点击遮罩是否关闭（默认 true） */
  closeOnBackdrop?: boolean;
  widthClass?: string;
}

/** 通用弹窗：遮罩 + 卡片 + 标题 + 关闭按钮。 */
export default function Modal({
  open,
  onClose,
  title,
  children,
  closeOnBackdrop = true,
  widthClass = 'w-[420px] max-w-[92vw]',
}: ModalProps) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-warm-900/40"
      onClick={() => {
        if (closeOnBackdrop) onClose();
      }}
    >
      <div
        className={`relative rounded-2xl bg-white p-6 shadow-xl max-h-[88vh] overflow-y-auto ${widthClass}`}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded text-warm-400 hover:bg-warm-100 transition-colors"
          title="关闭"
        >
          <X size={16} />
        </button>

        {title && <h3 className="mb-4 text-base font-semibold text-warm-800 pr-6">{title}</h3>}
        {children}
      </div>
    </div>
  );
}
