"""B0 延迟实测：连续跑 N 次小段生成，报告 p50/p95。

决定 Phase B 走"分支预渲染"(A) 还是"真实时"(B) 的关键数据。
需要 Replicate 余额；余额为 0 时直接报阻塞，不花一分钱。

用法：python3 b0_latency.py --runs 5 --reference reference/mixamo/qf1_combo.mp4
"""
import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import produce  # noqa: E402

WAN = "wan-video/wan-2.2-animate-replace"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--reference", default="")
    ap.add_argument("--fighter", default="IRON JAW")
    a = ap.parse_args()

    if not a.reference or not os.path.exists(a.reference):
        print("需要 --reference 指向一个真实 mp4 底片（先跑 pipeline/blender/batch_render.py）",
              file=sys.stderr)
        sys.exit(2)

    bal = produce.check_balance()
    print("Replicate balance: %s" % bal)
    if bal == 0 or bal == "0":
        print("BLOCKED: Replicate 余额为 0。先充值 ~$300（待用户点头），B0 才能跑。",
              file=sys.stderr)
        sys.exit(3)

    ref_url = produce.upload_local(a.reference)
    portrait = produce.portrait_path(a.fighter)
    lat = []
    for i in range(a.runs):
        t0 = time.time()
        try:
            produce.replicate_run(WAN, {"video": ref_url, "character_image": portrait,
                                        "resolution": "720p", "merge_audio": True},
                                  "/tmp/b0_%d.json" % i)
            dt = time.time() - t0
            lat.append(dt)
            print("run %d: %.1fs" % (i + 1, dt))
        except Exception as e:
            print("run %d FAILED: %s" % (i + 1, e), file=sys.stderr)
    if not lat:
        print("all runs failed", file=sys.stderr)
        sys.exit(1)
    p50 = statistics.median(lat)
    p95 = sorted(lat)[max(0, int(len(lat) * 0.95) - 1)]
    print("p50=%.1fs p95=%.1fs over %d runs" % (p50, p95, len(lat)))
    if p95 > 600:
        print("VERDICT: p95 > 10min → 真实时(B)路线冻结，只走分支预渲染(A)")
    else:
        print("VERDICT: p95 <= 10min → 真实时(B)路线可行，可试点")


if __name__ == "__main__":
    main()
