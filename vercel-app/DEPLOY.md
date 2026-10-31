# BRAWLVERSE API — Vercel 部署说明

架构：Vercel Python Serverless Functions + Postgres（`DATABASE_URL`）。
前端（GitHub Pages 纯静态）通过 `API_BASE` 连它；booker 后台是 `/admin.html`。

## 0. 准备两样东西

1. **Vercel Token**：vercel.com → 头像 → Settings → Tokens → Create
   （给 Muse 用 `vercel deploy`；也可以你本地 `vercel login` 后我远程指挥）
2. **Postgres 连接串**：三选一
   - Vercel Postgres（Vercel 项目 → Storage → Create → Postgres，最省事）
   - Neon（你 ad-scope 用过同款）
   - Supabase
   拿到 `DATABASE_URL`（`postgresql://...`，要带 `?sslmode=require` 的那串）

## 1. 部署

```bash
cd vercel-app
vercel deploy --prod
# 首次会问：link 到哪个项目 → 建新项目 brawlverse-api
```

## 2. 配环境变量（Vercel 项目 → Settings → Environment Variables）

- `DATABASE_URL` = 你的 postgres 连接串
- `ADMIN_TOKEN` = 强口令（booker 后台登录用）

配完 **Redeploy** 一次生效。

## 3. 接前端

`site/episodes.html`：

```js
const API_BASE = 'https://brawlverse-api.vercel.app';  // 换成你的实际域名
```

推送后 GitHub Pages 自动更新。API 不可达时页面降级为本地计数。

## 4. Booker 后台

`https://<你的vercel域名>/admin.html`，输 ADMIN_TOKEN。

## 防刷（v2）

- 浏览器真指纹：canvas + WebGL + 屏幕 + 时区 + 语言 + 硬件，并双种子哈希
- 后端另存 `ip_ua` 哈希，后台查原始投票时可识别"多设备同 IP"刷票
- 一设备一回合一票（改投=更新）、同 IP 60 秒 20 票限频
- 开源级指纹，防普通刷票够用；决赛前可再叠 Turnstile（v3）
