import useOverviewStore from '@/stores/overviewStore';

export default function Footer() {
  const sampleCount = useOverviewStore((s) => s.kpi?.sample_count);

  return (
    <footer className="h-8 bg-white border-t border-warm-200 flex items-center justify-center px-6 flex-shrink-0">
      <span className="text-xs text-warm-400">
        {typeof sampleCount === 'number'
          ? `明鉴・财税票・万景 · ${sampleCount} 家匿名企业数据`
          : '明鉴・财税票・万景 · 匿名企业数据'}
      </span>
    </footer>
  );
}
