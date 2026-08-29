import { describe, expect, it } from 'vitest';
import {
  normalizeFraudRows,
  normalizeAuthenticityRows,
  normalizeFraudBatch,
  normalizeAuthenticityBatch,
} from '@/api/risk';

describe('normalizeFraudRows', () => {
  it('maps top_flags batch object to table rows', () => {
    const rows = normalizeFraudRows({
      sample_count: 10,
      top_flags: [
        {
          enterprise_id: 'e1',
          display_label: '粤·制造·中型',
          industry_l1: '制造',
          fraud_composite_score: 88,
          fraud_risk_level: '高风险',
          scbm_mismatch_score: 70,
          red_invoice_score: 60,
          concentration_score: 50,
        },
      ],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].enterprise_id).toBe('e1');
    expect(rows[0].fraud_risk_level).toBe('high');
    expect(rows[0].fraud_composite_score).toBe(88);
  });

  it('returns empty array for empty batch (never invents demo rows)', () => {
    expect(normalizeFraudRows({ top_flags: [] })).toEqual([]);
    expect(normalizeFraudRows(null)).toEqual([]);
  });
});

describe('normalizeAuthenticityRows', () => {
  it('maps top_suspicious batch object to table rows', () => {
    const rows = normalizeAuthenticityRows({
      sample_count: 5,
      top_suspicious: [
        {
          enterprise_id: 'a1',
          display_label: '苏·批发·小型',
          authenticity_score: 42,
          cross_avg_deviation: 0.35,
          cross_suspicious: true,
        },
      ],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].enterprise_id).toBe('a1');
    expect(rows[0].cross_suspicious).toBe(true);
    expect(rows[0].authenticity_score).toBe(42);
  });

  it('does not default missing cross_suspicious to true', () => {
    const rows = normalizeAuthenticityRows({
      top_suspicious: [{ enterprise_id: 'a1', authenticity_score: 40 }],
    });
    expect(rows[0].cross_suspicious).toBeUndefined();
  });
});

describe('normalizeFraudBatch KPI', () => {
  it('uses sample_count/flagged_count/avg from batch not list length', () => {
    const batch = normalizeFraudBatch({
      sample_count: 193,
      flagged_count: 12,
      avg_composite: 41.5,
      top_flags: [{ enterprise_id: 'e1', fraud_composite_score: 90 }],
    });
    expect(batch.rows).toHaveLength(1);
    expect(batch.sample_count).toBe(193);
    expect(batch.flagged_count).toBe(12);
    expect(batch.avg_composite).toBe(41.5);
  });
});

describe('normalizeAuthenticityBatch KPI', () => {
  it('uses batch suspicious_count and avg, not top_N length', () => {
    const batch = normalizeAuthenticityBatch({
      sample_count: 100,
      suspicious_count: 7,
      avg_authenticity_score: 68.2,
      top_suspicious: [
        { enterprise_id: 'a1', authenticity_score: 40, cross_suspicious: true },
        { enterprise_id: 'a2', authenticity_score: 35, cross_suspicious: true },
      ],
    });
    expect(batch.rows).toHaveLength(2);
    expect(batch.sample_count).toBe(100);
    expect(batch.suspicious_count).toBe(7);
    expect(batch.avg_authenticity_score).toBe(68.2);
  });
});
