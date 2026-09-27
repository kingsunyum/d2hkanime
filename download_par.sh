#!/usr/bin/env bash
# 并发批量下载：把 urls.txt 分成 N 片并行跑（每片一个 download.sh 进程）
# 用法: ./download_par.sh [并发数]      # 默认 3
#        JOBS=4 ./download_par.sh
# 环境变量同 download.sh（INPUT/OUTDIR/LOG 等会透传给各分片）
set -u
export TERM=xterm
HERE="$(cd "$(dirname "$0")" && pwd)"
N="${1:-${JOBS:-3}}"
[[ "$N" =~ ^[1-9][0-9]*$ ]] || { echo "并发数必须是正整数: $N"; exit 1; }

OUTDIR="${OUTDIR:-/mnt/z4pro/video/儿童/我们这一家}"
echo "[$(date +%T)] 启动并发下载：$N 片 → $OUTDIR"
pids=()
for k in $(seq 1 "$N"); do
  SHARD="$k/$N" "$HERE/download.sh" 1 999999 &
  pids+=($!)
done
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
echo "[$(date +%T)] 全部分片完成 rc=$rc"
exit $rc
