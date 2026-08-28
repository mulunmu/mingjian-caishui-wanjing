USE `bill_tax_fusion_dwd_standrad`;
/*
 Navicat Premium Data Transfer

 Source Server         : SOURCE_DB_HOST
 Source Server Type    : MySQL
 Source Server Version : 50737 (5.7.37)
 Source Host           : SOURCE_DB_HOST:3306
 Source Schema         : bill_tax_fusion_dwd_standrad

 Target Server Type    : MySQL
 Target Server Version : 50737 (5.7.37)
 File Encoding         : 65001

 Date: 04/07/2025 23:29:23
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for syx_address_phone_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_address_phone_info`;
CREATE TABLE `syx_address_phone_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '客户地址电话信息',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '授权批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '企业税号',
  `taxpayer_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人名称',
  `yxrq` datetime NOT NULL COMMENT '客户信息验证有效日期',
  `source_section` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '客户信息来源板块',
  `source_taxno` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '客户信息来源批次号',
  `address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '地址',
  `phone_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '电话',
  `lkrq` datetime NULL DEFAULT NULL COMMENT '落库日期',
  `additional_Info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '其他信息',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uni_taxp_yxrq`(`taxpayer_id`, `yxrq`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '客户地址电话信息表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_approved_collection_info_dqde
-- ----------------------------
DROP TABLE IF EXISTS `syx_approved_collection_info_dqde`;
CREATE TABLE `syx_approved_collection_info_dqde`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '核定征收信息-定期定额核定信息查询',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `collection_items` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目',
  `ynsjye` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '应纳税经营额',
  `sl` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税率',
  `hdse` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '核定税额',
  `wdqzdbz` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '未达起征点标志',
  `hdzxqq` datetime NULL DEFAULT NULL COMMENT '核定执行期起',
  `hdzxqz` datetime NULL DEFAULT NULL COMMENT '核定执行期止',
  `zxhdbz` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '最新核定标志',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '核定征收信息-定期定额核定信息查询' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_approved_collection_info_sds
-- ----------------------------
DROP TABLE IF EXISTS `syx_approved_collection_info_sds`;
CREATE TABLE `syx_approved_collection_info_sds`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '核定征收信息-企业所得税',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `hdqxq` datetime NULL DEFAULT NULL COMMENT '核定期限起',
  `hdqxz` datetime NULL DEFAULT NULL COMMENT '核定期限止',
  `sjzxqz` datetime NULL DEFAULT NULL COMMENT '实际执行期止',
  `table_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收方式',
  `yssdl` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '应税所得率',
  `ynssde` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '年核定应纳税所得额',
  `sdse` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '年核定所得税额',
  `yjqx` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '企业所得税预缴期限',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '核定征收信息-企业所得税' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_approved_collection_info_yhs
-- ----------------------------
DROP TABLE IF EXISTS `syx_approved_collection_info_yhs`;
CREATE TABLE `syx_approved_collection_info_yhs`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '核定征收信息-印花税',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `collection_items` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目',
  `hdlx` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '核定类型',
  `hdzxqq` datetime NULL DEFAULT NULL COMMENT '核定执行期起',
  `hdzxqz` datetime NULL DEFAULT NULL COMMENT '核定执行期止',
  `sjzxqz` datetime NULL DEFAULT NULL COMMENT '实际执行期止',
  `hdrq` datetime NULL DEFAULT NULL COMMENT '核定日期',
  `hdjsyj` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '核定计税依据',
  `hdbl` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '核定比例',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '核定征收信息-印花税' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_auditing
-- ----------------------------
DROP TABLE IF EXISTS `syx_auditing`;
CREATE TABLE `syx_auditing`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '订单 ',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '创建时间',
  `aydjrq` datetime NULL DEFAULT NULL COMMENT '案源等级日期',
  `ajlymc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '案件来源名称',
  `jcztmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '稽查状态名称',
  `wfwzlxdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '违法违章类型代码',
  `jclxdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '稽查类型代码',
  `ajclyjdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '案件处理意见代码',
  `ajlydm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '案件来源代码',
  `jcztdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '稽查状态代码',
  `ajmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '案件名称',
  `nsrsbh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税识别 ',
  `wfwzlxmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '违法违章类型名称',
  `ajclyjmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '案件处理意件名称',
  `jclxmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '稽查类型名称',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `jcajjl` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '稽查案件结论',
  `cbskze` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '查补税款总额',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_bank_account_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_bank_account_info`;
CREATE TABLE `syx_bank_account_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '客户地址电话信息',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '授权批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '企业税号',
  `taxpayer_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人名称',
  `yxrq` datetime NOT NULL COMMENT '客户信息验证有效日期',
  `source_section` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '客户信息来源板块',
  `source_taxno` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '客户信息来源批次号',
  `bank_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '银行',
  `account` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '银行账号',
  `lkrq` datetime NULL DEFAULT NULL COMMENT '落库日期',
  `additional_Info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '其他信息',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uni_taxp_yxrq`(`taxpayer_id`, `yxrq`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '客户银行资料信息表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_cash_flow
-- ----------------------------
DROP TABLE IF EXISTS `syx_cash_flow`;
CREATE TABLE `syx_cash_flow`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '现金流量表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `wjxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件序号',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '行次',
  `bqje` decimal(20, 4) NULL DEFAULT NULL COMMENT '本期金额',
  `sqje` decimal(20, 4) NULL DEFAULT NULL COMMENT '上期金额',
  `bnljje` decimal(20, 4) NULL DEFAULT NULL COMMENT '本年金额',
  `report_type` int(11) NULL DEFAULT NULL COMMENT '报表类型(1:企业会计制度月报,2:企业会计制度年报,3:企业会计准则月报,4:企业会计准则年报,5:小企业会计准则月报,6:小企业会计准则年报))',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `deadline` datetime NULL DEFAULT NULL COMMENT '申报期限',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志 ',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'ID ',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表时期',
  `table_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型',
  `table_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型代码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 7759792 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业现金流量表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_season
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_season`;
CREATE TABLE `syx_corporate_income_season`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '企业所得税-月(季)度申报表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `wjxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件序号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `accumulative_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '累计金额',
  `current_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '本期金额',
  `project_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '父项目类型',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `project_sub_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '子项目类型',
  `table_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收方式(A:查账征收B:核定征收)',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `bureau` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局（大税区）',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `deadline` datetime NULL DEFAULT NULL COMMENT '申报期限',
  `should_pay_amt` decimal(20, 4) NULL DEFAULT NULL COMMENT '应补退税额',
  `change_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '更正类型',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志',
  `invalid_date` datetime NULL DEFAULT NULL COMMENT '作废日期',
  `new_levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目名称 ',
  `levy_project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目代码 ',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'ID ',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表时期',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2258383 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业所得税纳税申报信息（季度）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_season_header
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_season_header`;
CREATE TABLE `syx_corporate_income_season_header`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '企业所得税纳税申报信息（季度表头）',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `project_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目类型',
  `project_sub_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '子项目类型',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `one_quarter_begin` decimal(14, 2) NULL DEFAULT NULL COMMENT '一季度季初',
  `one_quarter_end` decimal(14, 2) NULL DEFAULT NULL COMMENT '一季度季末',
  `second_quarter_begin` decimal(14, 2) NULL DEFAULT NULL COMMENT '二季度季初',
  `second_quarter_end` decimal(14, 2) NULL DEFAULT NULL COMMENT '二季度季末',
  `three_quarter_begin` decimal(14, 2) NULL DEFAULT NULL COMMENT '三季度季初',
  `three_quarter_end` decimal(14, 2) NULL DEFAULT NULL COMMENT '三季度季末',
  `four_quarter_begin` decimal(14, 2) NULL DEFAULT NULL COMMENT '四季度季初',
  `four_quarter_end` decimal(14, 2) NULL DEFAULT NULL COMMENT '四季度季末',
  `quarter_average` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '季度平均值',
  `project_value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目值',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业所得税纳税申报信息（季度表头）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year`;
CREATE TABLE `syx_corporate_income_year`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '企业所得税-年度申报表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `wjxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件序号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '金额',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `table_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收方式(A:查账征收B:核定征收)',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `project_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目类型',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `deadline` datetime NULL DEFAULT NULL COMMENT '申报期限',
  `should_pay_amt` decimal(20, 4) NULL DEFAULT NULL COMMENT '应补退税额',
  `change_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '更正类型',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志',
  `invalid_date` datetime NULL DEFAULT NULL COMMENT '作废日期',
  `new_levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目名称 ',
  `levy_project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目代码 ',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'ID ',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表时期',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1262643 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业所得税纳税申报信息（年度）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_cbzc
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_cbzc`;
CREATE TABLE `syx_corporate_income_year_cbzc`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《一般企业成本支出明细表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '金额',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《一般企业成本支出明细表》（A102010）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_enterprise_gdinfo
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_enterprise_gdinfo`;
CREATE TABLE `syx_corporate_income_year_enterprise_gdinfo`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《企业所得税年度纳税申报基础信息表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `shareholder_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '股东名称',
  `credentials_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '证件种类',
  `credentials_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '证件号码',
  `investment_ratio` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '投资比例',
  `tzsyje` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '当年（决议日）分配的股息、红利等权益性投资收益金额',
  `nationality` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '国籍（注册地址）',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《企业所得税年度纳税申报基础信息表》（A000000）gd' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_enterprise_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_enterprise_info`;
CREATE TABLE `syx_corporate_income_year_enterprise_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《企业所得税年度纳税申报基础信息表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `project_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目类型',
  `project_sub_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '子项目类型',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `project_value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目值',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《企业所得税年度纳税申报基础信息表》（A000000）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_gxjs
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_gxjs`;
CREATE TABLE `syx_corporate_income_year_gxjs`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《高新技术企业优惠情况及明细表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目类型',
  `project_sub_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '子项目类型',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `project_value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目值',
  `this_year` decimal(20, 4) NULL DEFAULT NULL COMMENT '本年度',
  `previous_year` decimal(20, 4) NULL DEFAULT NULL COMMENT '前一年度',
  `previous_two_year` decimal(20, 4) NULL DEFAULT NULL COMMENT '前二年度',
  `total` decimal(20, 4) NULL DEFAULT NULL COMMENT '合计',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《高新技术企业优惠情况及明细表》（A107041）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_jmsds
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_jmsds`;
CREATE TABLE `syx_corporate_income_year_jmsds`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《减免所得税优惠明细表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '金额',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《减免所得税优惠明细表》（A107040）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_msjjsr
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_msjjsr`;
CREATE TABLE `syx_corporate_income_year_msjjsr`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《免税、减计收入及加计扣除优惠明细表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '金额',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《免税、减计收入及加计扣除优惠明细表》（A107010）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_qjfy
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_qjfy`;
CREATE TABLE `syx_corporate_income_year_qjfy`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《期间费用明细表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `xsfy` decimal(20, 4) NULL DEFAULT NULL COMMENT '销售费用',
  `xsfy_jwzf` decimal(20, 4) NULL DEFAULT NULL COMMENT '销售费用其中:境外支付',
  `glfy` decimal(20, 4) NULL DEFAULT NULL COMMENT '管理费用',
  `glfy_jwzf` decimal(20, 4) NULL DEFAULT NULL COMMENT '管理费用其中:境外支付',
  `cwfy` decimal(20, 4) NULL DEFAULT NULL COMMENT '财务费用',
  `cwfy_jwzf` decimal(20, 4) NULL DEFAULT NULL COMMENT '财务费用其中:境外支付',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《期间费用明细表》（A104000）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_qysr
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_qysr`;
CREATE TABLE `syx_corporate_income_year_qysr`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《一般企业收入明细表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '金额',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《一般企业收入明细表》（A101010）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_yffy
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_yffy`;
CREATE TABLE `syx_corporate_income_year_yffy`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《研发费用加计扣除优惠明细表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '金额（数量）',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《研发费用加计扣除优惠明细表》（A107012）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_corporate_income_year_zgxc
-- ----------------------------
DROP TABLE IF EXISTS `syx_corporate_income_year_zgxc`;
CREATE TABLE `syx_corporate_income_year_zgxc`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '《职工薪酬支出及纳税调整明细表》',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `zzje` decimal(20, 4) NULL DEFAULT NULL COMMENT '账载金额',
  `sjfse` decimal(20, 4) NULL DEFAULT NULL COMMENT '实际发生额',
  `ssgdkcl` decimal(20, 4) NULL DEFAULT NULL COMMENT '税收规定扣除率',
  `jzkce` decimal(20, 4) NULL DEFAULT NULL COMMENT '以前年度累计结转扣除额',
  `ssje` decimal(20, 4) NULL DEFAULT NULL COMMENT '税收金额',
  `nstzje` decimal(20, 4) NULL DEFAULT NULL COMMENT '纳税调整金额',
  `ndkce` decimal(20, 4) NULL DEFAULT NULL COMMENT '累计结转以后年度扣除额',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '《职工薪酬支出及纳税调整明细表》（A105050）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_credit_level
-- ----------------------------
DROP TABLE IF EXISTS `syx_credit_level`;
CREATE TABLE `syx_credit_level`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '纳税信用等级',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `credit_point` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '评价分数',
  `credit_level` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税务征信等级，枚举值[A、B、C、D、M、不参评、暂无、该纳税人还未终审完成]',
  `year` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '年度',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `credit_level_detail_list` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '纳税信用评价指标扣分记录',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 26821 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '纳税信用等级' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_declaration_correction
-- ----------------------------
DROP TABLE IF EXISTS `syx_declaration_correction`;
CREATE TABLE `syx_declaration_correction`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '申报更正表',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `id_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '序号',
  `bureau` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `original_declaration_date` datetime NULL DEFAULT NULL COMMENT '原申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `refund_amount_before_change` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '更正前应补退税额',
  `already_change_times` int(11) NULL DEFAULT NULL COMMENT '已更正次数',
  `voucher_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '凭证序号',
  `declaration_tax` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报税额',
  `declaration_deadline` datetime NULL DEFAULT NULL COMMENT '申报期限',
  `payment_tax` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '应纳税额',
  `state` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '状态',
  `tax_deadline_expires` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '是否超过纳税期限',
  `latest_operation_date` datetime NULL DEFAULT NULL COMMENT '最新操作日期',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `latest_declaration_date` datetime NULL DEFAULT NULL COMMENT '最新申报日期',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '申报更正表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_declaration_correction_records
-- ----------------------------
DROP TABLE IF EXISTS `syx_declaration_correction_records`;
CREATE TABLE `syx_declaration_correction_records`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '申报更正记录表',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `bureau` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志',
  `correction_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '更正类型',
  `should_pay_amt` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '应补退税额',
  `content_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '数据类型',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '申报更正记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_declaration_latest_correction
-- ----------------------------
DROP TABLE IF EXISTS `syx_declaration_latest_correction`;
CREATE TABLE `syx_declaration_latest_correction`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '最新申报文件更正表',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `id_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '序号',
  `bureau` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `original_declaration_date` datetime NULL DEFAULT NULL COMMENT '原申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `refund_amount_before_change` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '更正前应补退税额',
  `already_change_times` int(11) NULL DEFAULT NULL COMMENT '已更正次数',
  `voucher_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '凭证序号',
  `declaration_tax` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报税额',
  `declaration_deadline` datetime NULL DEFAULT NULL COMMENT '申报期限',
  `payment_tax` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '应纳税额',
  `state` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '状态',
  `tax_deadline_expires` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '是否超过纳税期限',
  `latest_operation_date` datetime NULL DEFAULT NULL COMMENT '最新操作日期',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `latest_declaration_date` datetime NULL DEFAULT NULL COMMENT '最新申报日期',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `content_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '数据类型',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '最新申报文件更正表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_enterprise_change_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_enterprise_change_info`;
CREATE TABLE `syx_enterprise_change_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '企业变更信息',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `bgrq` datetime NULL DEFAULT NULL COMMENT '变更日期',
  `bgxmmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '变更项目名称',
  `bgxmdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '变更项目代码',
  `bgqnr` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '变更前内容',
  `bghnr` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '变更后内容',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业变更信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_enterprise_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_enterprise_info`;
CREATE TABLE `syx_enterprise_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '企业基本信息',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `register_city` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '登记城市',
  `registered_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '注册类型',
  `registered_date` datetime NULL DEFAULT NULL COMMENT '注册日期',
  `legal_person_mobile_phone` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '法人移动电话',
  `start_business_date` datetime NULL DEFAULT NULL COMMENT '开业日期',
  `register_currencies` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '注册币种',
  `legal_person_id_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '法定代表人证件号码',
  `employees_number` int(11) NULL DEFAULT NULL COMMENT '从业人数',
  `register_county` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '登记区域',
  `legal_person_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '法人名称',
  `end_operation_date` datetime NULL DEFAULT NULL COMMENT '生产经营日期止',
  `tax_collector_id_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '办税人证件号码',
  `industry_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '行业类别',
  `taxpayer_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人资格类型',
  `taxpayer_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人名称',
  `operation_location_mobile` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '生产经营地联系电话',
  `bureau` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局（大税区）',
  `business_address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '生产经营地址',
  `finance_manager_id_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '财务负责人证件号码',
  `try_accounting_system` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '试用会计制度',
  `legal_person_credentials_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '法定代表人证件名称',
  `state_operation_date` datetime NULL DEFAULT NULL COMMENT '生产经营日期起',
  `business_scope` varchar(2500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '经营范围',
  `register_province` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '登记省份',
  `tax_collector_credentials_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '办税人证件名称',
  `register_address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '注册登记地址',
  `register_capital` decimal(20, 4) NULL DEFAULT NULL COMMENT '注册资本',
  `finance_manager_credentials_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '财务负责人证件类型',
  `tax_collector_mobile_phone` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '办税人移动电话',
  `finance_manager_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '财务负责人姓名',
  `nsrztmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人状态名称',
  `register_location_mobile` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '注册地联系电话',
  `finance_manager_mobile_phone` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '财务负责人移动电话',
  `tax_collector_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '办税人名称',
  `nsrztdm` int(11) NULL DEFAULT NULL COMMENT '纳税人状态代码',
  `industry_segments` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '细分产业',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `legal_person_name_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `legal_person_id_number_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `legal_person_mobile_phone_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `finance_manager_name_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `finance_manager_mobile_phone_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `finance_manager_id_number_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `tax_collector_mobile_phone_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `tax_collector_id_number_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `operation_location_mobile_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `business_address_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `register_address_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `register_location_mobile_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `tax_collector_name_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `bureau_detail` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局（具体税局）',
  `bureau_detail_dm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局代码（具体税局）',
  `hydm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '行业代码',
  `registered_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '注册类型代码',
  `legal_person_credentials_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '法定代表人证件类型代码',
  `tax_collector_credentials_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '办税人证件类型代码',
  `finance_manager_credentials_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '财务负责人证件类型代码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 7007 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业基本信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_general_institution_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_general_institution_info`;
CREATE TABLE `syx_general_institution_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '总机构信息',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `general_branch_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '总分机构类型',
  `general_taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '总机构统一社会信用代码（纳税人识别代码）',
  `general_institution_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '总机构名称',
  `general_institution_legal_person_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '总机构法定代表人姓名',
  `general_institution_address` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '总机构注册地址',
  `general_institution_postal_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '总机构邮政编码',
  `general_institution_mobile_phone` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '总机构联系电话',
  `general_institution_business_scope` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '总机构经营范围',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '总机构信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_investor_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_investor_info`;
CREATE TABLE `syx_investor_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '投资方信息',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tzfmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '投资方名称',
  `tzfjjxzdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '投资方经济性质代码',
  `tzfjjxzmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '投资方经济性质（名称 ）',
  `tzbl` int(11) NULL DEFAULT NULL COMMENT '投资比例 %',
  `zjzldm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '证件种类代码',
  `zjzlmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '证件种类名称',
  `zjhm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '证件号码',
  `gj` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '国籍',
  `tzje` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '投资金额',
  `address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '地址',
  `currencies` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '币种',
  `currencies_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '币种金额',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '投资方信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_invoice
-- ----------------------------
DROP TABLE IF EXISTS `syx_invoice`;
CREATE TABLE `syx_invoice`  (
  `id` bigint(20) NOT NULL,
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `sign` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '进销项表示',
  `fpzl` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票种类（code）',
  `fpdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票代码',
  `fphm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票号码',
  `kprq` datetime NULL DEFAULT NULL COMMENT '开票日期',
  `ssyf` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属月份',
  `hjje` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '金额(不含税)；二手车发票对应“车价合计',
  `hjse` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税额',
  `jshj` decimal(20, 4) NULL DEFAULT NULL COMMENT '价税合计 ',
  `zfbz` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志',
  `xfsh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方税号',
  `xfmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方名称',
  `xfdzdh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方地址电话',
  `xfyhzh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方银行资料',
  `gfsh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方税号',
  `gfmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方名称',
  `gfdzdh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方地址电话',
  `gfyhzh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方银行资料',
  `jym` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '校验码',
  `lzdmhm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '红冲发票代码号码组合',
  `cllx` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '车辆类型',
  `clsbdh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '车辆识别代号/车架号码',
  `cpxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '厂牌型号',
  `hgzh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '合格证号',
  `cd` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '产地',
  `sjdh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商检单号',
  `jkzmsh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '进口证明书号',
  `xcrs` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '限乘人数',
  `dw` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '吨位',
  `slv` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税率',
  `kpr` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '开票人',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `bz` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '备注',
  `invoice_source` int(11) NULL DEFAULT NULL COMMENT '发票来源0：pc,1：h5以及其他',
  `state` int(11) NULL DEFAULT NULL COMMENT '发票状态：0：正常，1：作废，2：红冲，3：失控，4：异常',
  `gfid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方id',
  `xfid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方id',
  `xfsh_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方税号',
  `xfmc_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方名称',
  `gfsh_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方税号',
  `gfmc_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方名称',
  `xfyhzh_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方银行资料',
  `xfdzdh_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方地址电话',
  `gfyhzh_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方银行资料',
  `gfdzdh_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方地址电话',
  `kpr_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '开票人',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `fpzl_zh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票种类（中文）',
  `d_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `sdphm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '数电票号码',
  `check_date` datetime NULL DEFAULT NULL COMMENT '勾选时间',
  `check_state` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '勾选状态',
  `fdjhm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发动机号码',
  `hc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '是否红冲',
  `zsfp` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '是否正数发票',
  `invoice_origin` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票来源名称',
  `invoice_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '状态',
  `risk_level` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票风险等级',
  `verify` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票查验标识,true查验false未查验',
  `invoice_time` datetime NULL DEFAULT NULL COMMENT '开票时间',
  `zfrq` datetime NULL DEFAULT NULL COMMENT '作废日期',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_jshj`(`jshj`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '发票' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_invoice_details
-- ----------------------------
DROP TABLE IF EXISTS `syx_invoice_details`;
CREATE TABLE `syx_invoice_details`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '发票货物详情表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `taxpayer_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `invoice_id` bigint(20) NULL DEFAULT NULL,
  `ggxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '规格型号',
  `spmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商品名称',
  `jldw` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '计量单位',
  `hsdj` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商品单价',
  `bw_spdj` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商品（不含税）单价',
  `spsl` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商品数量',
  `je` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '金额（不含税）（元）',
  `slv` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税率',
  `se` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税额（元）',
  `fpmxxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票明细序号',
  `scbm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商品编码',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `hsdj_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商品单价',
  `bw_spdj_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商品（不含税）单价',
  `spsl_tm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '商品数量',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `nlsv` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '零税率（枚举为“免税”“不征税”）',
  `fpdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票代码',
  `fphm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '发票号码',
  `sdphm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '数电票号码',
  `specific_business_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '特定业务类型',
  `jshj` decimal(20, 4) NULL DEFAULT NULL COMMENT '价税合计 ',
  `specific_business_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '特定业务类型代码',
  `xfsh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方税号',
  `xfmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方名称',
  `gfsh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方税号',
  `gfmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方名称',
  `kprq` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '开票日期',
  `sign` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '进销项表示',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_invoice_id`(`invoice_id`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 25616288 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '发票商品明细' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_invoice_overview_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_invoice_overview_info`;
CREATE TABLE `syx_invoice_overview_info`  (
  `id` bigint(20) NOT NULL COMMENT '开票概览信息',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '授权批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `invoice_total_amount` decimal(14, 2) NULL DEFAULT NULL COMMENT '发票总额度',
  `current_month` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '当前月份',
  `available_invoice_amount` decimal(14, 2) NULL DEFAULT NULL COMMENT '可用发票额度',
  `available_paper_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '当前可用纸票数量',
  `blue_invoice_amount` decimal(14, 2) NULL DEFAULT NULL COMMENT '蓝字发票开具金额',
  `red_invoice_amount` decimal(14, 2) NULL DEFAULT NULL COMMENT '红字发票开具金额',
  `use_paper_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '已开具纸票数量',
  `blue_invoice_cumulative_amount` decimal(14, 2) NULL DEFAULT NULL COMMENT '蓝字发票累计税额',
  `blue_invoice_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '蓝字发票数量',
  `red_invoice_cumulative_amount` decimal(14, 2) NULL DEFAULT NULL COMMENT '红字发票累计税额',
  `red_invoice_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '红字发票数量',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '开票概览信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_red_invoices_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_red_invoices_info`;
CREATE TABLE `syx_red_invoices_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '红字发票信息登记表',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `gxsf` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购销身份',
  `xfnsrmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方纳税人名称',
  `xfnsrsbh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '销方纳税人识别号',
  `gfnsrmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方纳税人名称',
  `gfnsrsbh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '购方纳税人识别号',
  `lpsdphm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '蓝票数电票号码',
  `lzfpdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '蓝字发票代码',
  `lzfphm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '蓝字发票号码',
  `lzkprq` datetime NULL DEFAULT NULL COMMENT '蓝字开票日期',
  `lzfpje` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '蓝字发票金额',
  `lzfpse` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '蓝字发票税额',
  `hztzdbh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '红字通知单编号',
  `fqsj` datetime NULL DEFAULT NULL COMMENT '发起时间',
  `hpsdphm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '红票数电票号码',
  `hzfpdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '红字发票代码',
  `hzfphm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '红字发票号码',
  `hzkprq` datetime NULL DEFAULT NULL COMMENT '红字开票日期',
  `hzfpje` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '红字发票金额',
  `hzfpse` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '红字发票税额',
  `clsj` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '处理时间',
  `chyy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '冲红原因',
  `qrjkp` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '确认即开票',
  `zt` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '确认单状态',
  `bz` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '红字发票信息登记表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_social_declaration
-- ----------------------------
DROP TABLE IF EXISTS `syx_social_declaration`;
CREATE TABLE `syx_social_declaration`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '社保申报信息',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `levy_sub_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收子品目',
  `type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型(正常申报,补缴申报)',
  `fee_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '费种',
  `fee_rate` decimal(20, 4) NULL DEFAULT NULL COMMENT '费率',
  `payment_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '本期应缴费额（元）',
  `should_payment_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '应缴费额（元）',
  `payment_base` decimal(20, 4) NULL DEFAULT NULL COMMENT '缴费基数',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `payment_people_number` int(11) NULL DEFAULT NULL COMMENT '缴费人数',
  `levy_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目',
  `bureau` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局（大税区）',
  `deduction_payment_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '抵缴费额（元）',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `deadline` datetime NULL DEFAULT NULL COMMENT '申报期限',
  `levy_project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目代码 ',
  `levy_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目代码 ',
  `enrollment_number` int(11) NULL DEFAULT NULL COMMENT '参保人数 ',
  `payment_method` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '缴纳方式',
  `levy_sub_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收子品目代码',
  `fee_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '费种代码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 590865 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '社保申报信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_sub_institution_info
-- ----------------------------
DROP TABLE IF EXISTS `syx_sub_institution_info`;
CREATE TABLE `syx_sub_institution_info`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '分机构信息',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `sub_taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '分机构统一社会信用代码（纳税人识别代码）',
  `sub_institution_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '分机构名称',
  `sub_institution_address` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '分机构注册地址',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '分机构信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_finance_balance_season
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_finance_balance_season`;
CREATE TABLE `syx_tax_finance_balance_season`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '资产负债表-月（季）度报表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `wjxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件序号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `report_type` int(11) NULL DEFAULT NULL COMMENT '报表类型(1:企业会计制度月报,2:企业会计制度年报,3:企业会计准则月报,4:企业会计准则年报,5:小企业会计准则月报,6:小企业会计准则年报)',
  `type` int(11) NULL DEFAULT NULL COMMENT '资产负债类型,1:资产,2:负债及所有者权益',
  `initial_balance` decimal(20, 4) NULL DEFAULT NULL COMMENT '年初数',
  `ending_balance` decimal(20, 4) NULL DEFAULT NULL COMMENT '期末数',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `project_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目类型',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志 ',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'ID ',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表时期',
  `table_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型',
  `table_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型代码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 5207389 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业资产负债表（月/季度）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_finance_balance_year
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_finance_balance_year`;
CREATE TABLE `syx_tax_finance_balance_year`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '资产负债表-年度报表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `wjxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件序号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `report_type` int(11) NULL DEFAULT NULL COMMENT '报表类型(1:企业会计制度月报,2:企业会计制度年报,3:企业会计准则月报,4:企业会计准则年报,5:小企业会计准则月报,6:小企业会计准则年报)',
  `type` int(11) NULL DEFAULT NULL COMMENT '资产负债类型,1:资产,2:负债及所有者权益',
  `initial_balance` decimal(20, 4) NULL DEFAULT NULL COMMENT '年初数',
  `ending_balance` decimal(20, 4) NULL DEFAULT NULL COMMENT '期末数',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `project_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目类型',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志 ',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'ID ',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表时期',
  `table_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型',
  `table_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型代码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1275675 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业资产负债表（年度）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_finance_profit_season
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_finance_profit_season`;
CREATE TABLE `syx_tax_finance_profit_season`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '利润-月（季）度报表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `wjxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件序号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `report_type` int(11) NULL DEFAULT NULL COMMENT '报表类型(1:企业会计制度月报,2:企业会计制度年报,3:企业会计准则月报,4:企业会计准则年报,5:小企业会计准则月报,6:小企业会计准则年报))',
  `current_year_accumulative_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '本年累计数',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `sqje` decimal(20, 4) NULL DEFAULT NULL COMMENT '上期金额',
  `current_month_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '本期金额',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志 ',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'ID ',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表时期',
  `table_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型',
  `table_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型代码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2762034 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业利润表（月/季度）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_finance_profit_year
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_finance_profit_year`;
CREATE TABLE `syx_tax_finance_profit_year`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '利润-年度报表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `wjxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件序号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `report_type` int(11) NULL DEFAULT NULL COMMENT '报表类型(1:企业会计制度月报,2:企业会计制度年报,3:企业会计准则月报,4:企业会计准则年报,5:小企业会计准则月报,6:小企业会计准则年报))',
  `current_year_accumulative_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '本年累计数',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `last_year_accumulative_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '上年累计数',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志 ',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'ID ',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表时期',
  `table_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型',
  `table_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表类型代码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 677010 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '利润-年度报表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_illega
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_illega`;
CREATE TABLE `syx_tax_illega`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '企业涉税违法违章信息',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `zywfwzsdmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '违法违章手段名称',
  `wfwzlxdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '违法违章类型代码',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `larq` datetime NULL DEFAULT NULL COMMENT '立案日期',
  `djrq` datetime NULL DEFAULT NULL COMMENT '登记日期',
  `wfwzztmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '违法违章状态名称',
  `clcfjdrq` datetime NULL DEFAULT NULL COMMENT '处理处罚时间',
  `xgzt` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '限改状态',
  `nsrsbh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税识别号',
  `zywfwzss` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '违法违章事实',
  `zywfwzsddm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '违法违章手段代码',
  `wfwzlxmc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '违法违章类型名称',
  `wfwzztdm` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '违法违章状态代码',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 8388 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业涉税违法违章信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_interaction
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_interaction`;
CREATE TABLE `syx_tax_interaction`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '银税互动',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申请（授信）日期',
  `bank_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '银行名称',
  `loan_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '贷款金额',
  `bank_product` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '产品名称',
  `loan_balance` decimal(20, 4) NULL DEFAULT NULL COMMENT '贷款余额',
  `status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '状态',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 22177 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '银税互动' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_payment
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_payment`;
CREATE TABLE `syx_tax_payment`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '完税信息',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `tax_attributes` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税款属性',
  `tax_payable` decimal(20, 4) NULL DEFAULT NULL COMMENT '应缴税款',
  `jsyj` decimal(20, 4) NULL DEFAULT NULL COMMENT '计税依据',
  `tax_paid` decimal(20, 4) NULL DEFAULT NULL COMMENT '已缴税款',
  `tax_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税款状态',
  `jkqx` datetime NULL DEFAULT NULL COMMENT '缴款期限',
  `sl` decimal(20, 4) NULL DEFAULT NULL COMMENT '税率',
  `bureau` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局（大税区）',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `payment_date` datetime NULL DEFAULT NULL COMMENT '缴款日期',
  `collection_items` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目',
  `extra_info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '多余信息',
  `tax_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税款种类',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `xssr` decimal(20, 4) NULL DEFAULT NULL COMMENT '销售收入',
  `storage_time` datetime NULL DEFAULT NULL COMMENT '入库时间',
  `tax_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税款种类代码',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称代码',
  `collection_items_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目代码',
  `enrollment_number` int(11) NULL DEFAULT NULL COMMENT '参保人数 ',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 519120 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '完税信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_type_determination
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_type_determination`;
CREATE TABLE `syx_tax_type_determination`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '税种认定信息',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `collection_items` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目',
  `levy_sub_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收子目',
  `effect_time_begin` datetime NULL DEFAULT NULL COMMENT '有效期起',
  `effect_time_end` datetime NULL DEFAULT NULL COMMENT '有效期止',
  `unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税期限',
  `declare_deadline` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报期限',
  `pay_deadline` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '缴款期限',
  `tax_rate` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税率或单位税额',
  `collection_method` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收方式',
  `collection_rate` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收率',
  `main_tax_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '主附税标志',
  `is_effective` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '当前是否有效',
  `industry` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '行业',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '税种认定信息' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_value_added
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_value_added`;
CREATE TABLE `syx_tax_value_added`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '企业增值税申报表',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `wjxh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件序号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `current_goods` decimal(20, 4) NULL DEFAULT NULL COMMENT '本期数-货物及劳务',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `project_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目类型',
  `current_year_accumulative_service` decimal(20, 4) NULL DEFAULT NULL COMMENT '本年累计-服务、不动产和无形资产',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  `column_sequence` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '栏次',
  `immediate_retreat_year_accumulative_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '即征即退项目-本年累计',
  `taxpayer_type` int(11) NULL DEFAULT NULL COMMENT '纳税人类型：0：一般纳税人1：小规模纳税人',
  `current_year_accumulative_goods` decimal(20, 4) NULL DEFAULT NULL COMMENT '本年累计-货物及劳务',
  `general_month_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '一般项目-本月数',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目名称',
  `current_service` decimal(20, 4) NULL DEFAULT NULL COMMENT '本期数-服务、不动产和无形资产',
  `general_year_accumulative_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '—般项目-本年累计',
  `immediate_retreat_month_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '即征即退项目-本月数',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `deadline` datetime NULL DEFAULT NULL COMMENT '申报期限',
  `should_pay_amt` decimal(20, 4) NULL DEFAULT NULL COMMENT '应补退税额',
  `change_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '更正类型',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志',
  `invalid_date` datetime NULL DEFAULT NULL COMMENT '作废日期',
  `new_levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目名称 ',
  `levy_project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目代码 ',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'ID ',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '报表时期',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 8909195 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业增值税申报表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_tax_value_added_header
-- ----------------------------
DROP TABLE IF EXISTS `syx_tax_value_added_header`;
CREATE TABLE `syx_tax_value_added_header`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '企业增值税纳税申报信息（表头，针对一般纳税人）',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `uuid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '申报唯一id',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `industry` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属行业',
  `taxpayer_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人名称',
  `legal_person_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '法定代表人姓名',
  `register_address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '注册地址',
  `business_address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '生产经营地址',
  `bank_account` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '开户银行',
  `account_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '开户账号',
  `registered_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '登记注册类型',
  `company_mobile_phone` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '电话号码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '企业增值税纳税申报信息（表头，针对一般纳税人）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_taxpayer_type
-- ----------------------------
DROP TABLE IF EXISTS `syx_taxpayer_type`;
CREATE TABLE `syx_taxpayer_type`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '纳税人资格类型表',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `taxpayer_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人资格类型',
  `taxpayer_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人资格类型代码',
  `yxqq` datetime NULL DEFAULT NULL COMMENT '有效期起',
  `yxqz` datetime NULL DEFAULT NULL COMMENT '有效期止',
  `invalid_mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '作废标志',
  `sjzzrq` datetime NULL DEFAULT NULL COMMENT '数据终止日期',
  `sequence` int(11) NULL DEFAULT NULL COMMENT '顺序',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `tax_no`(`tax_no`) USING BTREE,
  INDEX `order_id`(`order_no`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '纳税人资格类型表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_transaction
-- ----------------------------
DROP TABLE IF EXISTS `syx_transaction`;
CREATE TABLE `syx_transaction`  (
  `id` bigint(20) NOT NULL,
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `ZZSSBXQ_LIST` json NULL COMMENT '增值税申报详情',
  `SBXX_LIST` json NULL COMMENT '纳税申报数据',
  `LRBXX_LIST_ADJ` json NULL COMMENT '企业利润表-已规范',
  `ZCFZBXX_LIST_ADJ` json NULL COMMENT '企业资产负债表-已规范',
  `NSRJCXX` json NULL COMMENT '企业基础数据',
  `LRBXX_LIST` json NULL COMMENT '企业利润表',
  `SDSSBXQ_LIST` json NULL COMMENT '所得税申报详情',
  `ZCFZBXX_LIST` json NULL COMMENT '企业资产负债表',
  `LXRXX_LIST` json NULL COMMENT '企业联系人信息',
  `QYBGDJXX_LIST` json NULL COMMENT '企业变更信息',
  `ZSXX_LIST` json NULL COMMENT '税款征收信息',
  `TZFXX_LIST` json NULL COMMENT '企业投资方信息',
  `QYWFWZXX_LIST` json NULL COMMENT '企业涉税违法违章信息',
  `SWJCXX_LIST` json NULL COMMENT '企业稽查信息',
  `SXYGX_LIST` json NULL COMMENT '企业上下游',
  `channel_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '订单来源渠道',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `taxpayer_id`(`taxpayer_id`, `order_no`, `tax_no`) USING BTREE,
  INDEX `create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '纳税基础数据（微风企加工数据）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for syx_vat_arrears_tax
-- ----------------------------
DROP TABLE IF EXISTS `syx_vat_arrears_tax`;
CREATE TABLE `syx_vat_arrears_tax`  (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '欠税信息',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '纳税人识别号',
  `order_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务订单号',
  `tax_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集批次号',
  `create_time` datetime NULL DEFAULT NULL COMMENT '数据创建时间',
  `begin_date` datetime NULL DEFAULT NULL COMMENT '所属时期起',
  `end_date` datetime NULL DEFAULT NULL COMMENT '所属时期止',
  `tax_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税款种类',
  `declaration_date` datetime NULL DEFAULT NULL COMMENT '申报日期',
  `levy_project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `supplement_tax_amount` decimal(20, 4) NULL DEFAULT NULL COMMENT '应补税额（元）',
  `tax_paid` decimal(20, 4) NULL DEFAULT NULL COMMENT '已缴税款（元）',
  `tax_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税款状态',
  `bureau` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '所属税务局（大税区）',
  `payment_limit_date` datetime NULL DEFAULT NULL COMMENT '缴款期限',
  `project_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目',
  `collection_items` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目',
  `channel_source` int(11) NULL DEFAULT NULL COMMENT '订单来源渠道',
  `levy_project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收项目代码',
  `collection_items_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '征收品目代码',
  `project_name_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '项目代码',
  `tax_type_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税款种类代码',
  `tax_status_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '税款状态代码',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_tax_no`(`tax_no`) USING BTREE,
  INDEX `idx_order_no`(`order_no`) USING BTREE,
  INDEX `idx_create_time`(`create_time`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 6090 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '欠税信息' ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
