# BRAWLVERSE P2-full — 部署说明

后端：FastAPI + SQLite，一个 Docker 容器即跑。前端（GitHub Pages 纯静态）通过 `API_BASE` 连它。

## 1. 启动后端（新加坡服务器或任何 VPS）

```bash
cd brawlverse
cp server/.env.example server/.env
# 把 server/.env 里的 ADMIN_TOKEN 换成强口令
docker compose up -d --build
curl localhost:8000/api/health   # {"ok":true}
```

## 2. 接入前端投票

打开 `site/episodes.html`，找到：

```js
const API_BASE = ''; // e.g. 'https://api.example.com' after deploy
```

填上后端公网地址（建议套一层 HTTPS 反代，如 Nginx/Caddy）：

```js
const API_BASE = 'https://api.brawlverse.example.com';
```

重新推送 site/ 到 GitHub，Pages 自动更新。API 不可达时页面自动降级为浏览器本地计数，不会白屏。

## 3. Booker 后台

浏览器打开 `http://服务器IP:8000/admin/`，输入 ADMIN_TOKEN：
- 开/关某场比赛的投票
- 推进回合（Round 2 → 自动开新一轮投票）
- 实时看三选项票数条
- 新建对阵（QF5、半决赛、决赛）

## 4. 防刷说明（v1，老实话）

- 每设备每回合只计一票（改投=更新，不重复计）
- 同一 IP 60 秒内最多 20 票
- device_id 经 SHA256 哈希后存储，不存原始值
- 真设备指纹、验证码、登录态是 v2 的事；决赛这种关键场次建议届时再上

## 5. 数据

SQLite 文件在 docker volume `bv-data` 里（`/data/brawlverse.db`），备份拷走该文件即可。
