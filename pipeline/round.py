"""Friday Fight Night 分支预渲染：投票窗口内把 2 个战术分支都生成好。

用法：
  python3 round.py --bout qf1 --round 1 --tactic-a heavy --tactic-b dodge \\
      --fighter "IRON JAW" --reference reference/mixamo/qf1_combo.mp4
  # 默认 dry-run，只出计划和估算；加 --execute --yes 才真正花钱跑
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
import produce  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "rounds")
os.makedirs(OUTDIR, exist_ok=True)

TACTIC_LINE = {
    "heavy": "relentless power punches, pushing forward",
    "dodge": "slick head movement and counters",
    "guard": "tight defense, waiting for the opening",
}


def build_branch_brief(bout, rnd, branch, tactic, fighter, reference, duration):
    seg_id = "%s-r%s-%s" % (bout, rnd, branch)
    return {
        "bout_id": bout,
        "round": "%s-%s" % (rnd, branch),
        "fighters": [fighter],
        "segments": [{
            "id": seg_id,
            "type": "fight",
            "duration_s": duration,
            "fighter": fighter,
            "reference": reference,
            "note": "tactic=%s: %s" % (tactic, TACTIC_LINE.get(tactic, tactic)),
        }],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bout", required=True)
    ap.add_argument("--round", required=True)
    ap.add_argument("--tactic-a", required=True)
    ap.add_argument("--tactic-b", required=True)
    ap.add_argument("--fighter", required=True, help="出镜拳手（定妆照名）")
    ap.add_argument("--reference", default="", help="Mixamo 渲染底片 mp4")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--yes", action="store_true", help="二次确认，真的花钱")
    a = ap.parse_args()

    if not a.reference:
        print("WARN: 未给 --reference，execute 会失败；dry-run 仅看计划", file=sys.stderr)

    total_est = 0.0
    outputs = {}
    for branch, tactic in (("a", a.tactic_a), ("b", a.tactic_b)):
        brief = build_branch_brief(a.bout, a.round, branch, tactic, a.fighter,
                                   a.reference, a.duration)
        plan, est = produce.build_plan(brief)
        total_est += est
        print("branch %s (tactic=%s): %d steps, est $%.2f" % (branch, tactic, len(plan), est))
        for step in plan:
            print("   - %s <- %s" % (step.get("id"), step.get("model", "note")))
        if a.execute:
            if not a.yes:
                print("ABORT: --execute 需要同时加 --yes（花钱确认）", file=sys.stderr)
                sys.exit(2)
            workdir = os.path.join(HERE, "assets", "%s_r%s-%s" % (a.bout, a.round, branch))
            os.makedirs(workdir, exist_ok=True)
            produce.execute(plan, workdir)
            src = os.path.join(workdir, "%s-r%s-%s.mp4" % (a.bout, a.round, branch))
            dst = os.path.join(OUTDIR, "%s-r%s_%s.mp4" % (a.bout, a.round, branch))
            if os.path.exists(src):
                shutil.copy(src, dst)
                outputs[branch] = dst
                print("branch %s -> %s" % (branch, dst))

    print("TOTAL est: $%.2f for 2 branches" % total_est)
    if outputs:
        print("UPLOAD these to public URLs, then PATCH /api/admin/live with branch_a_url/branch_b_url:")
        for b, p in outputs.items():
            print("  %s: %s" % (b, p))


if __name__ == "__main__":
    main()
