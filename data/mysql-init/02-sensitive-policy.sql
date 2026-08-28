-- 运维说明（二次脱敏）：
-- ETL/API 不 SELECT taxpayer_name / 法人 / 身份证 / 地址 / business_scope / bureau_detail。
-- PG core_metrics 仅有 display_label（地区·行业·规模）。
-- 源库静止态敏感列仍可能存在；演示库请执行下方 UPDATE 或:
--   python -m scripts.redact_mysql_pii --apply

-- 安全只读视图（推荐应用账号仅 GRANT 视图，不 GRANT 基表敏感列）
CREATE OR REPLACE VIEW v_syx_enterprise_info_safe AS
SELECT
  id,
  taxpayer_id,
  order_no,
  tax_no,
  register_city,
  registered_type,
  registered_date,
  start_business_date,
  register_currencies,
  employees_number,
  register_county,
  end_operation_date,
  industry_type,
  taxpayer_type,
  -- 脱敏占位，不暴露真名
  CONCAT('ENT_', LEFT(taxpayer_id, 8)) AS taxpayer_name_mask,
  bureau,
  try_accounting_system,
  state_operation_date,
  register_province,
  register_capital,
  nsrztmc,
  nsrztdm,
  industry_segments,
  create_time,
  channel_source,
  bureau_detail,
  bureau_detail_dm,
  hydm,
  registered_type_code
FROM syx_enterprise_info;

-- 就地二次脱敏（不可逆；或用: python -m scripts.redact_mysql_pii --apply）
-- 现状：姓名/身份证/地址/电话多为 32-hex；经营范围与税局分局仍可读 → 必须擦除
UPDATE syx_enterprise_info SET
  business_scope = NULL,
  bureau_detail = NULL,
  taxpayer_name = IF(taxpayer_name REGEXP '^[0-9a-fA-F]{32}$', taxpayer_name, NULL),
  legal_person_name = IF(legal_person_name REGEXP '^[0-9a-fA-F]{32}$', legal_person_name, NULL),
  legal_person_id_number = IF(legal_person_id_number REGEXP '^[0-9a-fA-F]{32}$', legal_person_id_number, NULL),
  legal_person_mobile_phone = IF(legal_person_mobile_phone REGEXP '^[0-9a-fA-F]{32}$', legal_person_mobile_phone, NULL),
  register_address = IF(register_address REGEXP '^[0-9a-fA-F]{32}$', register_address, NULL),
  business_address = IF(business_address REGEXP '^[0-9a-fA-F]{32}$', business_address, NULL),
  finance_manager_name = IF(finance_manager_name REGEXP '^[0-9a-fA-F]{32}$', finance_manager_name, NULL),
  finance_manager_id_number = IF(finance_manager_id_number REGEXP '^[0-9a-fA-F]{32}$', finance_manager_id_number, NULL),
  finance_manager_mobile_phone = IF(finance_manager_mobile_phone REGEXP '^[0-9a-fA-F]{32}$', finance_manager_mobile_phone, NULL),
  tax_collector_name = IF(tax_collector_name REGEXP '^[0-9a-fA-F]{32}$', tax_collector_name, NULL),
  tax_collector_id_number = IF(tax_collector_id_number REGEXP '^[0-9a-fA-F]{32}$', tax_collector_id_number, NULL),
  tax_collector_mobile_phone = IF(tax_collector_mobile_phone REGEXP '^[0-9a-fA-F]{32}$', tax_collector_mobile_phone, NULL),
  operation_location_mobile = IF(operation_location_mobile REGEXP '^[0-9a-fA-F]{32}$', operation_location_mobile, NULL),
  register_location_mobile = IF(register_location_mobile REGEXP '^[0-9a-fA-F]{32}$', register_location_mobile, NULL);

-- 保留：bureau / industry_type / nsrztmc / registered_type（ETL 与 display_label 需要，粒度不足以唯一定位）
