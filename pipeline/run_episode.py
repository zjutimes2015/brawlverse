#!/usr/bin/env python3
"""一键跑单集：draft（脑）→ produce（手）→ assemble（合成）。

默认全程 dry-run（不花钱）；真跑：
  python3 run_episode.py --bout qf1 --a "IRON JAW" --b "VIPER" \\
      --feud "VIPER 在 EP0 反击 KO 了 JAW，JAW 走复仇线" --execute --yes

前置：
  OPENROUTER_API_KEY  (draft 用；没有就跳过 draft，用现成的 brief)
  Replicate 走 custom.replicate connector（helper 代跑，无需 token）
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def sh(*args):
    r = subprocess.run([sys.executable, *args])
    if r.returncode != 0:
        sys.exit("FAILED: " + " ".join(args))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bout", required=True)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--feud", default="")
    ap.add_argument("--round", default="1")
    ap.add_argument("--model", default="deepseek/deepseek-chat")
    ap.add_argument("--brief", default=None, help="跳过 draft，直接用现成 brief")
    ap.add_argument("--format", default="vertical", choices=["vertical", "horizontal"])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    brief_path = a.brief
    if not brief_path:
        if not a.feud:
            sys.exit("--feud 必填（或用 --brief 跳过 draft）")
        print("=== 1/3 draft（OpenRouter，几分钱）===")
        sh(os.path.join(HERE, "draft.py"), "--bout", a.bout, "--a", a.a, "--b", a.b,
           "--feud", a.feud, "--round", a.round, "--model", a.model)
        brief_path = os.path.join(HERE, "briefs", "%s_r%s.json" % (a.bout, a.round))
    else:
        print("=== 1/3 draft skipped（用现成 brief）===")

    print("=== 2/3 produce（Replicate）===")
    pargs = [os.path.join(HERE, "produce.py"), "--brief", brief_path]
    if a.execute:
        pargs += ["--execute"]
        if a.yes:
            pargs += ["--yes"]
    sh(*pargs)

    if a.execute and a.yes:
        print("=== 3/3 assemble（ffmpeg）===")
        sh(os.path.join(HERE, "assemble.py"), "--brief", brief_path, "--format", a.format)
    else:
        print("=== 3/3 assemble skipped（dry-run）===")
        print("真跑：加 --execute --yes")


if __name__ == "__main__":
    main()
