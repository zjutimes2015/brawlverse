# BRAWLVERSE 单集生产管线

脑（OpenRouter，便宜）→ 手（Replicate，大头）→ 合成（ffmpeg，免费）→ 手动发布（App 内配热门 BGM）。

## 前置

| 变量/条件 | 用途 | 状态 |
|---|---|---|
| `OPENROUTER_API_KEY` | draft 生成剧本 | 待用户给 key |
| Replicate connector | produce 跑模型 | 已接，余额 0 |
| 实拍动作库 | fight 片段的 `reference` | 待建（手机拍） |

## 跑法

```bash
cd pipeline

# 1. 只出剧本（几分钱），先看反转行不行
OPENROUTER_API_KEY=sk-... python3 draft.py --bout qf1 --a "IRON JAW" --b "VIPER" \
    --feud "VIPER 在 EP0 反击 KO 了 JAW，JAW 走复仇线"

# 2. 看执行计划+估算（不花钱）
python3 produce.py --brief briefs/qf1_r1.json

# 3. 一键全跑（真花钱，需二次确认）
python3 run_episode.py --bout qf1 --a "IRON JAW" --b "VIPER" \
    --feud "VIPER 在 EP0 反击 KO 了 JAW，JAW 走复仇线" --execute --yes
```

## 模型清单（输入 schema 2026-10-31 实锤）

| 环节 | 模型 | 输入 | 单价 |
|---|---|---|---|
| 定妆照 | google/nano-banana-2.1 | prompt/aspect_ratio=3:4 | ~$0.05/张 |
| 正赛 | wan-video/wan-2.2-animate-replace | video/character_image/resolution=720p | $0.08/s |
| 配音 | inworld/realtime-tts-2 | text/language=en | ~$0.005/s |
| 采访动起来 | cjwbw/sadtalker | driven_audio/source_image | ~$0.02/s |
| 对嘴型（可选） | sync/lipsync-2-pro | audio/video | ~$0.05/s |
| 收尾超分 | bria/video-increase-resolution | video_url/desired_increase=2x | ~$0.03/s |

定妆照缓存于 `assets/portraits/`（缺啥补啥，不重复花钱）。
本地文件自动经中转存储转公网 URL（48h 有效，跑单够用）。

## 数据回流（飞轮）

`vercel-app` 的 votes/bets/播放数据 → 下次 draft 时把"上期观众最吃哪段"喂给 OpenRouter → 剧本自动调优。效果数据→内容，这就是护城河。

## 安全

- 默认 dry-run；`--execute` 必须配 `--yes`，防手滑。
- 执行前自动查 Replicate 余额。
- BGM 永不在管线里加（平台热门曲库铁律）。

## 实拍动作库（reference/）

| 来源 | 目录 | 说明 |
|---|---|---|
| Mixamo 渲染（首选） | `reference/mixamo/` | mixamo.com 免费下 FBX（jab/cross/hook/uppercut 全套，商用免费），Blender 渲染成 mp4 |
| CC0 素材 | `reference/cc0/` | Pexels/Pixabay/Mixkit，搜 boxing training |
| 自拍 | `reference/shot/` | 手机拍，版权最干净 |

选定底片后，在 brief 的 segment.reference 里填路径或 URL，`produce.py` 会自动处理。
详见《BRAWLVERSE-实拍动作库方案-v1.0》。
