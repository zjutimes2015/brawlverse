#!/usr/bin/env python3
"""Step 1 — 脑：OpenRouter 生成单集 brief（分镜表 + 垃圾话台词 + 解说词）。

Usage:
  OPENROUTER_API_KEY=sk-... python3 draft.py --bout qf1 --a "IRON JAW" --b "VIPER" \\
      --feud "VIPER 在 EP0 反击 KO 了 JAW，JAW 走复仇线" --round 1

Output: briefs/<bout>_r<round>.json
"""
import argparse
import json
import os
import sys
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

FIGHTERS = {
    "IRON JAW": "重炮手，沉默寡言的力量型。EP0 被 VIPER 反击 KO，走复仇线。",
    "VIPER": "毒牙，狡猾的反击型拳手。EP0 赢家，嘴毒，喜欢心理战。",
    "SLEDGE": "拆迁，纯力量碾压型，拆迁队长人设。",
    "MONSOON": "风暴，速度连击型，来去如风。",
    "VOLT": "混沌，'计划？老子就是闪电'，不可预测。",
    "THE PROFESSOR": "秩序，每场比赛都有 14 步剧本，学院派。",
    "GOLIATH-7": "温柔巨人，8 人里最不想打架的那个，被迫应战。",
    "LA REINA": "女王，8 人里最想赢的那个，气场压制。",
}

SYSTEM = """你是 BRAWLVERSE 的 booker（剧情策划），WWE 式剧本娱乐，不是真实体育。
8 位 AI 拳手的人设如下：
%s

铁律：
1. 每集必须有反转（观众预期→出乎意料的翻转），3 分钟只变一个变量。
2. 必须有 before/after 视觉对比，3 秒内看得出来。
3. 单集 3 分钟 beat sheet：0:00 钩子 → 0:30 对峙 → 1:00 R1 埋反转 → 1:30 R2 战术投票点 → 2:00 R3 逆转 buff → 2:30 结局+下集预告。
4. 垃圾话台词必须符合拳手人设，英文，短促有力，适合 TTS 朗读（<20 词/条）。
5. 只输出 JSON，不要解释。

输出 JSON 结构：
{
  "segments": [
    {"id": "s1", "type": "fight", "duration_s": 30, "action": "动作描述（给换角色模型的实拍参考描述）", "reference": "实拍动作库文件名或描述"},
    {"id": "s2", "type": "trash_talk", "fighter": "拳手名", "line": "英文台词", "duration_s": 8}
  ],
  "commentary": [{"t": "0:05", "line": "英文解说词"}],
  "tactic_vote": {"question": "英文投票问题", "options": ["heavy", "dodge", "guard"]},
  "twist": "本集反转点一句话"
}"""


def call_openrouter(system, user, model):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        sys.exit("OPENROUTER_API_KEY not set")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.9,
    }).encode()
    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://zjutimes2015.github.io/brawlverse/",
                 "X-Title": "BRAWLVERSE booker"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    content = d["choices"][0]["message"]["content"]
    usage = d.get("usage", {})
    print("tokens: in=%s out=%s" % (usage.get("prompt_tokens"), usage.get("completion_tokens")),
          file=sys.stderr)
    return json.loads(content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bout", required=True)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--feud", required=True, help="恩怨一句话")
    ap.add_argument("--round", default="1")
    ap.add_argument("--model", default="deepseek/deepseek-chat",
                    help="cheap default; use anthropic/claude-* for quality")
    ap.add_argument("--outdir", default="briefs")
    a = ap.parse_args()

    personas = "\n".join("- %s：%s" % (k, v) for k, v in FIGHTERS.items())
    user = ("bout_id=%s round=%s\n%s vs %s\n恩怨：%s\n请输出本集 brief JSON。"
            % (a.bout, a.round, a.a, a.b, a.feud))
    brief = call_openrouter(SYSTEM % personas, user, a.model)
    brief["bout_id"] = a.bout
    brief["round"] = a.round
    brief["fighters"] = [a.a, a.b]

    os.makedirs(a.outdir, exist_ok=True)
    path = os.path.join(a.outdir, "%s_r%s.json" % (a.bout, a.round))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)
    print("brief -> " + path)
    print("twist: " + brief.get("twist", ""))


if __name__ == "__main__":
    main()
