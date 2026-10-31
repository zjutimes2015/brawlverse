# BRAWLVERSE API — Cloudflare Workers + D1 部署

## 前提

- Cloudflare 账号（已有，adaptlane.com 在上面）
- API Token：dash.cloudflare.com → My Profile → API Tokens → Create Token
  → 用 **Edit Cloudflare Workers** 模板，并加上 **D1** 读写权限

## 部署步骤（Muse 侧已备好代码，token 到位后一条条跑）

```bash
cd workers
export CLOUDFLARE_API_TOKEN=<你的token>

# 1. 建 D1 数据库（只需一次）
wrangler d1 create brawlverse
# 把输出的 database_id 填进 wrangler.toml 的 REPLACE_AFTER_CREATE

# 2. 建表 + 灌四场四分之一决赛
wrangler d1 execute brawlverse --file schema.sql

# 3. 设 booker 后台口令（强口令，只你知道）
wrangler secret put ADMIN_TOKEN

# 4. 发布
wrangler deploy
# → 得到 https://brawlverse-api.<你的子域>.workers.dev
```

## 接前端

`site/episodes.html` 里：

```js
const API_BASE = 'https://brawlverse-api.<你的子域>.workers.dev';
```

推送后 GitHub Pages 自动更新。API 不可达时页面降级为本地计数。

## Booker 后台

`https://brawlverse-api.<你的子域>.workers.dev/admin/`，输 ADMIN_TOKEN。

## 防刷（v2，已上线）

1. **浏览器指纹**：canvas + WebGL 渲染器 + 屏幕 + 时区 + 语言 + 硬件并发数，cyrb53 双种子哈希 → 同一浏览器稳定唯一
2. **IP+UA 双信号**：后端另存 `ip_ua` 哈希，booker 后台查原始投票时能一眼看出"几十个设备 ID 同一个 IP"这种刷票
3. **一设备一回合一票**（改投=更新）、同 IP 60 秒 20 票限频

老实话：这是开源级指纹（FingerprintJS 免费版同等水平），防普通刷票够用；职业黑产（改 UA、换 IP 池）要再叠 Turnstile 验证码，那是 v3 的事，决赛前再说。
