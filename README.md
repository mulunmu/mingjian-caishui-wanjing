# 明鉴 - 税务风险研判系统

基于税务数据的五维研判引擎（评分 / 真实性 / 反欺诈 / 基准 / 趋势）。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Vite + Zustand + Tailwind CSS + ECharts |
| 后端 | FastAPI + SQLAlchemy 2.x + PostgreSQL + Redis (可选) |
| AI | LiteLLM + DeepSeek (可选) |

## 快速启动

### 前置条件

- Python 3.10+
- Node.js 18+
- PostgreSQL 16 (可选，有内存回退)

### 开发模式（推荐）

**Windows:**
```bash
start.bat dev
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh dev
```

启动后访问：
- 前端: http://localhost:3000
- 后端 API: http://localhost:8000
- Swagger 文档: http://localhost:8000/docs

### 生产模式

```bash
start.bat prod
# 或
./start.sh prod
```

### 仅启动后端

```bash
start.bat backend
# 或
./start.sh backend
```

### 仅启动前端

```bash
start.bat frontend
# 或
./start.sh frontend
```

## 环境配置

后端环境变量在 `backend/.env` 文件中配置（首次启动时自动从 `.env.example` 复制）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://risk_user:risk_pass@localhost:5432/risk_db` | PostgreSQL 连接 |
| `REDIS_URL` | (空) | Redis 连接（可选，不配置则使用内存缓存） |
| `LLM_API_KEY` | (空) | LLM API Key（可选） |
| `AUTH_REQUIRED` | `false` | 是否强制认证 |
| `JWT_SECRET` | (内置演示密钥) | JWT 签名密钥 |
| `CORS_ORIGINS` | `*` | CORS 允许来源 |

## 项目结构

```
├── src/                    # 前端源码
│   ├── api/                # API 封装
│   ├── stores/             # Zustand 状态管理
│   ├── types/              # TypeScript 类型
│   ├── pages/              # 页面组件
│   ├── components/         # 通用组件
│   └── utils/              # 工具函数
├── backend/                # 后端源码
│   ├── app/
│   │   ├── api/v1/         # API 路由
│   │   ├── services/       # 业务逻辑
│   │   ├── models/         # 数据模型
│   │   └── main.py         # FastAPI 入口
│   └── requirements.txt
├── start.bat               # Windows 启动脚本
├── start.sh                # Linux/Mac 启动脚本
├── vite.config.ts          # Vite 配置
└── package.json
```

## API 接口

基础地址: `http://localhost:8000/api/v1`

- `POST /auth/login` - 登录
- `POST /auth/register` - 注册
- `POST /chat` - AI 对话
- `GET /risk/summary` - Dashboard 概览
- `GET /risk/warnings` - 预警清单
- `GET /risk/enterprise/{id}` - 企业画像
- `GET /risk/fraud` - 反欺诈分析
- `GET /risk/authenticity` - 经营真实性
- `GET /report/list` - 报告列表
- `POST /report/generate` - 生成报告
- `GET /report/{id}/download` - 下载报告

完整 API 文档: http://localhost:8000/docs
