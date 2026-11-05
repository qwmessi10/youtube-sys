# SMM 面板逆向文档

对 Telegram 机器人 `@AutoLakCloudbot`（AutoLak Cloud SMM 面板）的逆向成果，用于自动化提交 YouTube 推广任务（刷量）。

## 文件清单

| 文件 | 说明 |
|------|------|
| `REVERSE_FINDINGS.md` | 完整逆向文档：前端/后端地址、认证机制、关键接口、创建任务请求体、实测报文、字段映射、关键坑 |
| `autolak_client.py` | 可复用 Python 客户端（纯标准库，无第三方依赖），封装查余额 / 创建任务，可直接集成 Django 后台 |
| `network.log` | 真实抓包记录（含 `searchTaskRecord` 返回的任务字段结构） |
| `appsrc/` | 小程序前端源码（`index.html` + `index.js` 主包，约 3MB） |

## 核心结论速览

- 小程序前端：`https://saircaf.autolak.in/#/`（Vite + React 单页应用）
- 后端 API：`https://atpsv.autolak.in/client`
- 认证：`POST /user/publishTelegramAuth` 传 `tgUserId` 换 token（**不校验 Telegram 签名，只认 tgUserId**），后续请求带 `Authorization` + `Identifier` + `userType` + `tgUserId` 等头
- 创建任务：`POST /publish/sendTask`
- 查余额：`POST /user/balance`
- 任务记录：`POST /publish/searchTaskRecord`

## 关键坑

- 直连 API 会被 403（WAF），**必须带浏览器 User-Agent + Origin/Referer** 头
- `endTime` 按印度时区（UTC+5:30）发送
- `perUser`（每人奖励）后端要求 ≥ 2
- token 稳定不轮换（按 tgUserId 固定生成），但仍可能过期

## 安全提示

- 文档中的 token / tgUserId 等凭证来自本人账号，可能已过期；失效需重新登录小程序并从 localStorage 提取。
- 本仓库为私有仓库，凭证请勿外泄；若转公开需先脱敏。

## 相关实现

逆向成果已落地到后台的 **SMM 面板系统**（`backend/smm` app，账号 / 刷量任务 / 轮询刷量），需求见 `需求文档/SMM面板系统-需求文档.md`。
