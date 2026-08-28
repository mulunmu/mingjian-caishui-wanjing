import { useState } from 'react';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';

interface ReportActionsProps {
  reportId: string;
  onDownload: (id: string) => void;
  onSendEmail: (id: string, email: string) => void;
}

export default function ReportActions({
  reportId,
  onDownload,
  onSendEmail,
}: ReportActionsProps) {
  const [showEmail, setShowEmail] = useState(false);
  const [email, setEmail] = useState('');

  const handleSend = () => {
    if (email.trim()) {
      onSendEmail(reportId, email.trim());
      setShowEmail(false);
      setEmail('');
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          size="sm"
          onClick={() => onDownload(reportId)}
          icon={
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
          }
        >
          下载 PDF
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setShowEmail(!showEmail)}
          icon={
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="M22 7L12 13L2 7" />
            </svg>
          }
        >
          发送邮件
        </Button>
      </div>

      {showEmail && (
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Input
              label="收件邮箱"
              type="email"
              placeholder="example@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <Button variant="primary" size="sm" onClick={handleSend}>
            发送
          </Button>
        </div>
      )}
    </div>
  );
}
