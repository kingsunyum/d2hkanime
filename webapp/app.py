#!/usr/bin/env python3
"""动画下载前端 — FastAPI 后端
- 填写/粘贴 m3u8 链接、启动批量下载、实时显示进度条
- 显示挂载目录（NAS）容量与已下载文件
本地运行：python3 app.py  → http://127.0.0.1:8765
"""
import os, re, signal, subprocess, time, shutil
from pathlib import Path
from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse, JSONResponse

BASE = Path.home() / "workspace" / "anime"
SCRIPT = BASE / "download.sh"
URLS = BASE / "urls.txt"
LOG = BASE / "_web.log"
DEAD = BASE / "dead.txt"
NOTIFY_CONF = Path.home() / ".config" / "anime-notify.env"
NRE = Path.home() / "tools" / "N_m3u8DL-RE"
DEFAULT_OUTDIR = "/mnt/z4pro/video/儿童/我们这一家"
HERE = Path(__file__).resolve().parent

app = FastAPI(title="动画下载前端")
PROC: subprocess.Popen | None = None


_SHELLS = {"bash", "sh", "dash", "zsh", "busybox"}


def _is_download_cmdline(args: list[str], script: str) -> bool:
    """判断一条 argv 是否是下载脚本进程。
    只认「解释器 + 脚本路径」或「直接执行脚本」，不会被 `bash -c '…download.sh…'` 骗到。"""
    if not args:
        return False
    if args[0] == script:                              # 直接执行脚本
        return True
    if len(args) >= 2 and os.path.basename(args[0]) in _SHELLS and args[1] == script:
        return True                                    # bash /path/download.sh
    return False


def _pgrep_download():
    """扫描 /proc 找下载脚本进程，精确匹配脚本路径（不依赖 pgrep -f 的模糊匹配）。"""
    script = str(SCRIPT)
    pids = []
    for d in Path("/proc").glob("[0-9]*"):
        try:
            raw = (d / "cmdline").read_bytes()
        except Exception:
            continue
        args = [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]
        if _is_download_cmdline(args, script):
            try:
                pids.append(int(d.name))
            except ValueError:
                pass
    return pids


def running() -> bool:
    if PROC is not None and PROC.poll() is None:
        return True
    return bool(_pgrep_download())


def count_urls() -> int:
    if not URLS.exists():
        return 0
    n = 0
    for line in URLS.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip() and "$" in line:
            n += 1
    return n


def _pick_log(outdir: str):
    """优先用前端自己的日志；为空则回退到输出目录里的 _download.log"""
    if LOG.exists() and LOG.stat().st_size > 0:
        return LOG
    alt = Path(outdir) / "_download.log"
    return alt if alt.exists() else LOG


def parse_progress(outdir: str = DEFAULT_OUTDIR):
    """从日志解析每个条目的状态与当前下载百分比"""
    items, done, failed, skipped = [], 0, 0, 0
    current, current_pct = None, 0.0
    logf = _pick_log(outdir)
    if logf.exists():
        lines = logf.read_text(encoding="utf-8", errors="replace").splitlines()
        # 取“最后一轮”：优先当前进行中的一轮；若已收尾，则取其前一轮
        markers = [i for i, l in enumerate(lines) if "==== done:" in l]
        if markers and any(l.strip() for l in lines[markers[-1] + 1:]):
            start = markers[-1] + 1
        elif len(markers) >= 2:
            start = markers[-2] + 1
        else:
            start = 0
        for line in lines[start:]:
            m = re.search(r"\[\d{2}:\d{2}:\d{2}\] DOWNLOAD \(\d+\): (.+)$", line)
            if m:
                current = m.group(1).strip()
                items.append({"name": current, "status": "running", "pct": 0.0})
                continue
            m = re.search(r"\[\d{2}:\d{2}:\d{2}\] OK: (.+)$", line)
            if m:
                name = m.group(1).strip()
                done += 1
                for it in items:
                    if it["name"] == name:
                        it["status"], it["pct"] = "done", 100.0
                continue
            m = re.search(r"\[\d{2}:\d{2}:\d{2}\] FAIL\(rc=(\d+)\): (.+)$", line)
            if m:
                name = m.group(2).strip()
                failed += 1
                for it in items:
                    if it["name"] == name:
                        it["status"], it["pct"] = "fail", 0.0
                continue
            m = re.search(r"\[\d{2}:\d{2}:\d{2}\] SKIP \(exists\): (.+)$", line)
            if m:
                skipped += 1
                items.append({"name": m.group(1).strip(), "status": "done", "pct": 100.0})
                continue
            # 进度：形如 "  35/143 24.48%" ——取该行最大比例
            fr = re.findall(r"(\d+)/(\d+)\s+([\d.]+)%", line)
            if fr and current:
                best = max((int(a) / max(int(b), 1)) for a, b, _ in fr)
                current_pct = round(best * 100, 1)
                if items and items[-1]["name"] == current:
                    items[-1]["pct"] = current_pct
    return items, done, failed, skipped, current, current_pct


def disk_info(path: str):
    try:
        u = shutil.disk_usage(path)
        mp = Path(path).resolve()
        # 找挂载点
        while not os.path.ismount(mp) and mp != mp.parent:
            mp = mp.parent
        mounted = os.path.ismount(mp)
        return {
            "ok": True, "path": path, "mount": str(mp), "mounted": mounted,
            "total": u.total, "used": u.used, "free": u.free,
            "pct": round(u.used / u.total * 100, 1),
        }
    except Exception as e:
        return {"ok": False, "path": path, "error": str(e)}


def _read_conf() -> dict:
    """解析 ~/.config/anime-notify.env 为 dict（忽略注释/空行）"""
    d = {}
    try:
        for ln in NOTIFY_CONF.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return d


def _enabled_from(cfg: dict) -> bool:
    return str(cfg.get("NOTIFY_ENABLED", "1")).strip().lower() not in ("0", "false", "no", "off")


def notify_configured() -> bool:
    return bool(_read_conf().get("TELEGRAM_BOT_TOKEN"))


def notify_enabled() -> bool:
    return _enabled_from(_read_conf())


def set_notify_enabled(flag: bool) -> None:
    """原地更新 NOTIFY_ENABLED，保留其余配置，权限保持 600"""
    lines, found = [], False
    if NOTIFY_CONF.exists():
        for ln in NOTIFY_CONF.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("NOTIFY_ENABLED="):
                lines.append(f"NOTIFY_ENABLED={'1' if flag else '0'}")
                found = True
            else:
                lines.append(ln)
    if not found:
        lines.append(f"NOTIFY_ENABLED={'1' if flag else '0'}")
    NOTIFY_CONF.parent.mkdir(parents=True, exist_ok=True)
    NOTIFY_CONF.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(NOTIFY_CONF, 0o600)


def count_dead() -> int:
    """dead.txt 中确实出现在 urls.txt 里的死链条数"""
    if not DEAD.exists() or not URLS.exists():
        return 0
    names = {ln.split("$", 1)[0] for ln in
             URLS.read_text(encoding="utf-8", errors="replace").splitlines() if "$" in ln}
    return sum(1 for ln in DEAD.read_text(encoding="utf-8", errors="replace").splitlines()
               if ln.strip() and ln.strip() in names)


def load_times(outdir: str):
    """读取 _times.tsv（sname<TAB>start_epoch<TAB>end_epoch）"""
    p = Path(outdir) / "_times.tsv"
    d = {}
    if p.exists():
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = ln.split("\t")
            if len(parts) >= 3:
                s = int(parts[1]) if parts[1].isdigit() else None
                e = int(parts[2]) if parts[2].isdigit() else None
                d[parts[0]] = (s, e)
    return d


def list_downloads(outdir: str, limit=400):
    p = Path(outdir)
    if not p.is_dir():
        return []
    times = load_times(outdir)
    files = []
    for f in sorted(p.glob("*.mkv")):
        try:
            st = f.stat()
            s, e = times.get(f.name[:-4], (None, None))
            files.append({"name": f.name, "size": st.st_size, "mtime": int(st.st_mtime),
                          "start": s, "end": e or int(st.st_mtime)})
        except Exception:
            pass
    return files[-limit:]


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "index.html").read_text(encoding="utf-8")


@app.get("/api/state")
def state(outdir: str = DEFAULT_OUTDIR):
    items, ok_n, failed, skipped, current, current_pct = parse_progress(outdir)
    done = ok_n + skipped                     # SKIP(exists) 也算已完成
    urls_n = count_urls()
    dead = count_dead()
    total = max(urls_n - dead, 0)          # 可达集数（扣除死链）
    run = running()
    overall = round((done + failed) / total * 100, 1) if total else 0.0
    pending = max(total - done - failed, 0)
    return JSONResponse({
        "running": run,
        "outdir": outdir,
        "urls_count": urls_n,
        "dead": dead,
        "total": total,
        "done": done, "failed": failed,
        "pending": pending,
        "finished": (not run) and pending == 0 and total > 0,
        "notify_configured": notify_configured(),
        "notify_enabled": notify_enabled(),
        "autostart": autostart_enabled(),
        "current": current, "current_pct": current_pct,
        "overall_pct": overall,
        "items": items,
        "disk": disk_info(outdir),
        "files": list_downloads(outdir),
        "nre": NRE.exists(),
    })


@app.get("/api/urls_text")
def urls_text():
    return {"text": URLS.read_text(encoding="utf-8", errors="replace") if URLS.exists() else ""}


def derive_name(url: str) -> str:
    """从 m3u8 URL 推断一个可读的保存名（download.sh 要求 name$url 格式）"""
    m = re.search(r"/([^/]+)\.mp4/master\.m3u8", url)
    token = m.group(1) if m else None
    parts = [p for p in url.split("/") if p]
    series = parts[-3] if len(parts) >= 3 else ""
    if token and token.isdigit():
        base = f"EP{int(token)}"
        return f"{series} - {base}" if series else base
    if token:
        return f"{series} - {token}" if series else token
    tail = parts[-1] if parts else "video"
    tail = tail.split("?")[0].rsplit(".", 1)[0] or "video"
    return f"{series} - {tail}" if series else tail


def dedup_items(lines):
    """按 URL 和名称去重；同名不同 URL 保留先出现的。返回 (去重后列表, 丢弃数)"""
    seen_names, seen_urls, out = set(), set(), []
    for ln in lines:
        name, _, url = ln.partition("$")
        if url in seen_urls or name in seen_names:
            continue
        seen_urls.add(url)
        seen_names.add(name)
        out.append(ln)
    return out, len(lines) - len(out)


@app.post("/api/urls")
def save_urls(payload: dict = Body(...)):
    text = (payload.get("text") or "").replace("\r", "")
    lines = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if "$" in ln:
            lines.append(ln)                       # 已是 name$url
        elif ln.startswith("http"):
            lines.append(f"{derive_name(ln)}${ln}")  # 纯 URL，自动命名
    lines, dropped = dedup_items(lines)
    URLS.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {"ok": True, "count": len(lines), "dropped": dropped}


def ensure_outdir(outdir: str) -> tuple[bool, bool, str]:
    """确保目录存在。返回 (ok, created, error)。created=True 表示本次新建。"""
    p = Path(outdir)
    if p.is_dir():
        return True, False, ""
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, False, str(e)
    return True, True, ""


@app.post("/api/mkdir")
def mkdir_endpoint(payload: dict = Body(...)):
    """按前端输入的目录自动创建（如 /mnt/z4pro/video/儿童/工作细胞）"""
    outdir = (payload.get("outdir") or "").strip()
    if not outdir:
        return JSONResponse({"ok": False, "error": "目录为空"}, status_code=400)
    existed = Path(outdir).is_dir()
    ok, _created, err = ensure_outdir(outdir)
    if not ok:
        return JSONResponse({"ok": False, "outdir": outdir, "error": err}, status_code=500)
    return {"ok": True, "outdir": outdir, "created": not existed, "disk": disk_info(outdir)}


@app.post("/api/start")
def start(payload: dict = Body(default={})):
    if running():
        return JSONResponse({"ok": False, "error": "已有下载任务在运行"}, status_code=409)
    outdir = payload.get("outdir") or DEFAULT_OUTDIR
    sdir = int(payload.get("start") or 1)
    cnt = int(payload.get("count") or 999999)
    ok, _created, err = ensure_outdir(outdir)
    if not ok:
        return JSONResponse({"ok": False, "error": f"无法创建/访问输出目录: {err}"}, status_code=500)
    LOG.write_text("", encoding="utf-8")          # 本轮日志清空
    env = dict(os.environ, OUTDIR=outdir, LOG=str(LOG), TERM="xterm")
    global PROC
    PROC = subprocess.Popen([str(SCRIPT), str(sdir), str(cnt)],
                            cwd=str(BASE), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    return {"ok": True, "pid": PROC.pid, "outdir": outdir}


SVC_FILE = Path.home() / ".config" / "systemd" / "user" / "anime-download.service"
SVC_NAME = "anime-download.service"


def autostart_enabled() -> bool:
    """下载服务是否开机自启（由 systemd enable 状态决定）"""
    try:
        r = subprocess.run(["/usr/bin/systemctl", "--user", "is-enabled", SVC_NAME],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "enabled"
    except Exception:
        return False


def set_autostart(flag: bool) -> tuple[bool, str]:
    """开关 anime-download 开机自启（enable/disable，不动当前运行状态）"""
    act = "enable" if flag else "disable"
    try:
        r = subprocess.run(["/usr/bin/systemctl", "--user", act, SVC_NAME],
                           capture_output=True, text=True, timeout=20)
    except Exception as e:
        return False, str(e)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "未知错误").strip()
    return True, ""


@app.get("/api/autostart")
def get_autostart():
    return {"enabled": autostart_enabled(), "unit": SVC_NAME,
            "running": running()}


@app.post("/api/autostart")
def toggle_autostart(payload: dict = Body(...)):
    """开关「开机自动下载」：{enabled: true/false}。
    改的是 systemd 自启状态，不影响当前是否正在下载。"""
    flag = bool(payload.get("enabled"))
    ok, err = set_autostart(flag)
    if not ok:
        return JSONResponse({"ok": False, "error": err}, status_code=500)
    return {"ok": True, "enabled": flag}


@app.get("/api/notify")
def get_notify():
    cfg = _read_conf()
    return {"configured": bool(cfg.get("TELEGRAM_BOT_TOKEN")),
            "chat_id_set": bool(cfg.get("TELEGRAM_CHAT_ID")),
            "enabled": _enabled_from(cfg)}


@app.post("/api/notify")
def set_notify(payload: dict = Body(...)):
    """开关 Telegram 通知：{enabled: true/false}"""
    enabled = bool(payload.get("enabled"))
    try:
        set_notify_enabled(enabled)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return {"ok": True, "enabled": enabled}


@app.post("/api/notify_test")
def notify_test():
    if not notify_enabled():
        return JSONResponse({"ok": False, "out": "通知开关已关闭，未发送（可在界面重新开启）"}, status_code=200)
    script = BASE / "notify.sh"
    if not script.exists():
        return JSONResponse({"ok": False, "out": "notify.sh 不存在"}, status_code=404)
    r = subprocess.run([str(script), "🔔 测试通知：动画下载前端"],
                       capture_output=True, text=True, timeout=30)
    return {"ok": r.returncode == 0, "out": (r.stdout + r.stderr).strip()}


@app.post("/api/stop")
def stop():
    global PROC
    killed = []
    if PROC is not None and PROC.poll() is None:
        try:
            os.killpg(os.getpgid(PROC.pid), signal.SIGTERM); killed.append(PROC.pid)
        except Exception:
            pass
    # 兜底
    for pid in _pgrep_download():
        try:
            os.kill(pid, signal.SIGTERM); killed.append(pid)
        except Exception:
            pass
    time.sleep(0.5)
    return {"ok": True, "killed": killed}


@app.get("/api/log")
def log(tail: int = 120):
    if not LOG.exists():
        return {"lines": []}
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    clean = [l for l in lines if "\u2501" not in l]  # 去掉进度条噪声
    return {"lines": clean[-tail:]}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=int(os.environ.get("PORT", "8765")), log_level="warning")
