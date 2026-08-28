# 2.0 版本控制说明

## 现状

- **本目录已 `git init`**（2026-08-28）：`2.0/` 可作为独立仓库根，使 `.github/workflows/ci.yml` 可被 GitHub Actions 触发。
- 历史曾仅存在于 `1.0/.git`，且不跟踪 `2.0/` 路径，导致新版本无 diff/回滚。

## CI

| 文件 | 生效条件 |
|------|----------|
| `2.0/.github/workflows/ci.yml` | git 根 = `2.0/` |
| 仓库根 `.github/workflows/ci-2.0.yml` | git 根 = monorepo（含 `1.0/` + `2.0/`） |

## 密钥历史（P0-4）

`1.0` 仓库历史中仍可能残留 `sk-` / 内网 IP。工作区脱敏不够；开源前需：

1. 控制台**吊销**已泄露 API key  
2. 用 `git filter-repo`（或 BFG）重写历史后再 push（**破坏性操作，需负责人明确授权**）

本仓库不在未授权情况下执行历史重写。
