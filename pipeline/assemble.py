#!/usr/bin/env python3
"""Step 3 — 合成：ffmpeg 拼接 + 解说字幕烧录 + 响度归一。

BGM 故意不加：按铁律必须用平台热门曲库，App 内手动发布时配。

Usage:
  python3 assemble.py --brief briefs/qf1_r1.json --format vertical
Output: out/<bout>_r<round>.mp4 (+ .srt)
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

FORMATS = {
    "vertical": ("1080", "1920"),    # TikTok / Reels / Shorts
    "horizontal": ("1920", "1080"),  # YouTube 长视频
}


def srt_time(sec):
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    return "%02d:%02d:%02d,000" % (h, m, s)


def build_srt(commentary, path):
    """commentary: [{t: '0:05', line}] -> srt。t 支持 m:ss。"""
    cur = 0
    out = []
    for i, c in enumerate(commentary):
        t = c.get("t", "0:00")
        parts = t.split(":")
        sec = int(parts[0]) * 60 + int(float(parts[1])) if len(parts) == 2 else int(float(parts[0]))
        nxt = commentary[i + 1].get("t", None) if i + 1 < len(commentary) else None
        if nxt:
            np = nxt.split(":")
            end = int(np[0]) * 60 + int(float(np[1])) if len(np) == 2 else int(float(np[0]))
        else:
            end = sec + 4
        out.append("%d\n%s --> %s\n%s\n" % (i + 1, srt_time(sec), srt_time(end), c["line"]))
        cur = end
    open(path, "w", encoding="utf-8").write("\n".join(out))
    return path, cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", required=True)
    ap.add_argument("--format", default="vertical", choices=list(FORMATS))
    ap.add_argument("--assets", default=os.path.join(HERE, "assets"))
    ap.add_argument("--outdir", default=os.path.join(HERE, "out"))
    a = ap.parse_args()

    brief = json.load(open(a.brief, encoding="utf-8"))
    bout, rnd = brief["bout_id"], brief["round"]
    workdir = os.path.join(a.assets, "%s_r%s" % (bout, rnd))
    w, h = FORMATS[a.format]
    os.makedirs(a.outdir, exist_ok=True)

    # 收集成片段（按 brief 顺序，跳过缺失的）
    segs = []
    for seg in brief.get("segments", []):
        p = os.path.join(workdir, seg["id"] + ".mp4")
        if os.path.exists(p):
            segs.append(p)
        else:
            print("SKIP missing: " + p, file=sys.stderr)
    if not segs:
        sys.exit("no segments in " + workdir + " — 先跑 produce.py --execute")

    # concat
    lst = os.path.join(workdir, "concat.txt")
    open(lst, "w").write("".join("file '%s'\n" % s for s in segs))
    tmp = os.path.join(workdir, "concat.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", tmp], check=True)

    # 字幕
    srt = os.path.join(a.outdir, "%s_r%s.srt" % (bout, rnd))
    build_srt(brief.get("commentary", []), srt)

    # 缩放+字幕烧录+响度
    out = os.path.join(a.outdir, "%s_r%s_%s.mp4" % (bout, rnd, a.format))
    vf = ("scale=%s:%s:force_original_aspect_ratio=increase,"
          "crop=%s:%s,"
          "subtitles=%s:force_style='FontName=DejaVu Sans,FontSize=22,"
          "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,"
          "Outline=2,Alignment=2,MarginV=60'" % (w, h, w, h, srt.replace(":", "\\:")))
    subprocess.run(["ffmpeg", "-y", "-i", tmp, "-vf", vf,
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-c:a", "aac", "-b:a", "128k",
                    "-af", "loudnorm",
                    "-movflags", "+faststart", out], check=True)
    print("done -> " + out)
    print("字幕 -> " + srt)
    print("下一步：手动在 App 内发布，配平台热门 BGM。")


if __name__ == "__main__":
    main()
