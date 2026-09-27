#!/usr/bin/env bash
# WSL version of demo.bat — batch download m3u8 via N_m3u8DL-RE
# Usage: ./download.sh [start_index] [count]
set -u
# N_m3u8DL-RE (Spectre.Console) crashes (SIGABRT) when TERM=dumb; force a sane value
export TERM=xterm
HERE="$(cd "$(dirname "$0")" && pwd)"
NRE="${NRE:-$HOME/tools/N_m3u8DL-RE}"
INPUT="${INPUT:-$HOME/workspace/anime/urls.txt}"
DEADFILE="${DEADFILE:-$HOME/workspace/anime/dead.txt}"
OUTDIR="${OUTDIR:-/mnt/z4pro/video/儿童/我们这一家}"
LOG="${LOG:-$OUTDIR/_download.log}"

# HTTP headers —— 用环境变量覆盖（不要硬编码 Cookie）：
#   HTTP_COOKIE="your_cookie"  —— 如 Stream=8964
#   HTTP_ORIGIN="https://www.example.com"
#   HTTP_REFERER="https://www.example.com/"
HTTP_COOKIE="${HTTP_COOKIE:-}"
HTTP_ORIGIN="${HTTP_ORIGIN:-}"
HTTP_REFERER="${HTTP_REFERER:-}"
EXTRA_HEADERS=()
[[ -n "$HTTP_COOKIE"  ]] && EXTRA_HEADERS+=(-H "Cookie: ${HTTP_COOKIE}")
[[ -n "$HTTP_ORIGIN"  ]] && EXTRA_HEADERS+=(-H "Origin: ${HTTP_ORIGIN}")
[[ -n "$HTTP_REFERER" ]] && EXTRA_HEADERS+=(-H "Referer: ${HTTP_REFERER}")
START="${1:-1}"
COUNT="${2:-999999}"
# 并发分片线程数：--thread-count 1 会让分片串行下载（每片一次往返），实测 8 比 1 快约 20 倍
THREADS="${THREADS:-16}"

mkdir -p "$OUTDIR"
[[ -f "$INPUT" ]] || { echo "no input: $INPUT"; exit 1; }

# 单实例锁：防止重复启动造成孤儿/僵尸进程
LOCK="${LOCK:-$(dirname "$INPUT")/.download.lock}"
exec 9>"$LOCK"
flock -n 9 || { echo "[$(date +%T)] 已有下载实例在运行，退出" | tee -a "$LOG"; exit 1; }

# 收到 TERM/INT：终止并回收子进程（wait），避免留下僵尸
child=""; stopped=0; finished_ok=0
on_signal(){ stopped=1; if [[ -n "$child" ]]; then kill -TERM "$child" 2>/dev/null; wait "$child" 2>/dev/null; fi; exit 0; }
# 非正常结束（崩溃/被 kill）也发通知；手动停止不算
on_exit(){
  rc=$?
  [[ $stopped -eq 1 ]] && exit 0
  if [[ $finished_ok -ne 1 ]]; then
    "$HERE/notify.sh" "❌ 下载异常退出（rc=$rc）
目录: $OUTDIR
时间: $(date '+%F %H:%M:%S')" 2>/dev/null || true
  fi
}
trap on_signal TERM INT
trap on_exit EXIT

ok=0; fail=0; i=0; done_n=0
run_start=$(date +%s)
declare -A SEEN=()   # 本次运行已处理的名称（同名去重）
"$HERE/notify.sh" "⏬ 开始下载
列表: $(basename "$INPUT")
目录: $OUTDIR
时间: $(date '+%F %H:%M:%S')" 2>/dev/null || true
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"              # strip CR
  [[ -z "$line" ]] && continue
  [[ "$line" != *'$'* ]] && continue
  i=$((i+1))
  # 并发分片：SHARD="k/N" 表示本进程只处理第 k 片（k=1..N）
  if [[ -n "${SHARD:-}" ]]; then
    _si=${SHARD%%/*}; _sn=${SHARD##*/}
    (( (i - 1) % _sn != _si - 1 )) && continue
  fi
  (( i < START )) && continue
  (( done_n >= COUNT )) && break
  done_n=$((done_n+1))

  name="${line%%\$*}"
  url="${line#*\$}"
  # 同名去重：本次运行内重复名称只处理一次
  if [[ -n "${SEEN[$name]:-}" ]]; then
    echo "[$(date +%T)] SKIP (dup-name): $name" | tee -a "$LOG"
    continue
  fi
  SEEN[$name]=1
  # 已知 404 死链直接跳过（dead.txt 每行一个名称）
  if [[ -f "$DEADFILE" ]] && grep -Fxq -- "$name" "$DEADFILE"; then
    echo "[$(date +%T)] SKIP (known-404): $name" | tee -a "$LOG"
    continue
  fi
  # sanitize for filename: replace path-illegal chars
  sname="$(printf '%s' "$name" | tr '/\\:*?"<>|' '_________')"

  # 恢复中断的混流产物：只剩 *.MUX.mkv 时改名成正式名
  for m in "$OUTDIR/$sname"*MUX.mkv; do
    [[ -e "$m" ]] || continue
    tgt="${m%MUX.mkv}mkv"
    if [[ ! -e "$tgt" ]]; then mv -n -- "$m" "$tgt" && echo "[$(date +%T)] RECOVER: $(basename "$tgt")" | tee -a "$LOG"; fi
  done

  # skip if already done
  if ls "$OUTDIR/$sname"*.mkv >/dev/null 2>&1; then
    echo "[$(date +%T)] SKIP (exists): $sname" | tee -a "$LOG"
    ok=$((ok+1)); continue
  fi

  start_epoch=$(date +%s)
  echo "[$(date +%T)] DOWNLOAD ($done_n): $sname" | tee -a "$LOG"
  "$NRE" \
    "${EXTRA_HEADERS[@]}" \
    "$url" --thread-count "$THREADS" -sa all -sv all -ss all \
    -M format=mkv:muxer=ffmpeg \
    --save-name "$sname" --save-dir "$OUTDIR" >>"$LOG" 2>&1 &
  child=$!
  wait "$child"; rc=$?
  child=""
  if [[ $rc -eq 0 && -n "$(ls "$OUTDIR/$sname"*.mkv 2>/dev/null)" ]]; then
    end_epoch=$(date +%s)
    printf '%s\t%s\t%s\n' "$sname" "$start_epoch" "$end_epoch" >> "$OUTDIR/_times.tsv"
    echo "[$(date +%T)] OK: $sname" | tee -a "$LOG"; ok=$((ok+1))
  else
    echo "[$(date +%T)] FAIL(rc=$rc): $sname" | tee -a "$LOG"; fail=$((fail+1))
    if (( fail <= 10 )); then
      "$HERE/notify.sh" "❌ 下载失败
条目: $sname
原因: rc=$rc
目录: $OUTDIR
时间: $(date '+%F %H:%M:%S')" 2>/dev/null || true
    elif (( fail == 11 )); then
      "$HERE/notify.sh" "❌ 失败已超过 10 条，后续不再逐条通知（结束时汇总）" 2>/dev/null || true
    fi
  fi
done < "$INPUT"

echo "==== done: ok=$ok fail=$fail ====" | tee -a "$LOG"
finished_ok=1

# Telegram 完成通知（未配置则自动跳过）
elapsed=$(( $(date +%s) - run_start ))
if (( fail > 0 )); then title="⚠️ 动画下载结束（有失败）"; else title="🎬 动画下载完成"; fi
"$HERE/notify.sh" "$(printf '%s\n目录: %s\n结果: ok=%d  fail=%d\n耗时: %d 分 %d 秒\n时间: %s' \
  "$title" "$OUTDIR" "$ok" "$fail" $((elapsed/60)) $((elapsed%60)) "$(date '+%F %H:%M:%S')")" 2>/dev/null || true
