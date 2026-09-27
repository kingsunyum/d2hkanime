#!/usr/bin/env python3
"""从 _download.log 回填 _times.tsv（sname<TAB>start_epoch<TAB>end_epoch）。

日志里只有 HH:MM:SS，用同名 mkv 的 mtime 作为“完成”锚点来推算日期
（跨零点会自动按 -1 天修正）。
"""
import os, re, sys, datetime

OUT = sys.argv[1] if len(sys.argv) > 1 else "/mnt/z4pro/video/儿童/我们这一家"
LOG = os.path.join(OUT, "_download.log")
TSV = os.path.join(OUT, "_times.tsv")

dl_re = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\] DOWNLOAD \(\d+\): (.+)$")
ok_re = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\] OK: (.+)$")
sod = lambda h, m, s: int(h) * 3600 + int(m) * 60 + int(s)

last_dl, done = {}, {}
with open(LOG, encoding="utf-8", errors="replace") as fh:
    for line in fh:
        m = dl_re.search(line)
        if m:
            last_dl[m.group(4).strip()] = sod(*m.groups()[:3])
            continue
        m = ok_re.search(line)
        if m:
            name = m.group(4).strip()
            if name in last_dl:
                done[name] = (last_dl[name], sod(*m.groups()[:3]))

rows, missing = [], 0
for fn in os.listdir(OUT):
    if not fn.endswith(".mkv") or "MUX" in fn:
        continue
    name = fn[:-4]
    mtime = int(os.path.getmtime(os.path.join(OUT, fn)))
    if name in done:
        ss, es = done[name]
        base = datetime.datetime.fromtimestamp(mtime).replace(microsecond=0)
        end = base.replace(hour=es // 3600, minute=(es % 3600) // 60, second=es % 60)
        if abs(end.timestamp() - mtime) > 12 * 3600:          # 跨日修正
            end += datetime.timedelta(days=1 if end.timestamp() < mtime else -1)
        start = end.replace(hour=ss // 3600, minute=(ss % 3600) // 60, second=ss % 60)
        if start > end:                                        # 开始晚于完成 → 前一天
            start -= datetime.timedelta(days=1)
        rows.append((name, int(start.timestamp()), int(end.timestamp())))
    else:
        missing += 1
        rows.append((name, "", mtime))

rows.sort()
with open(TSV, "w", encoding="utf-8") as fh:
    for name, s, e in rows:
        fh.write(f"{name}\t{s}\t{e}\n")
print(f"写入 {TSV}: {len(rows)} 条（其中 {missing} 条无开始时间，仅有完成时间）")
