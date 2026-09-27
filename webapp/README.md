# d2hkanime

基于 N_m3u8DL-RE + ffmpeg 的 m3u8 批量下载脚本 + FastAPI Web 前端，支持实时进度、磁盘视图、Telegram 通知。

## 用法

```bash
# 批量下载
./download.sh

# 并发分片
./download_par.sh 3

# 前端（需 python3 + fastapi + uvicorn）
cd webapp && ./run.sh   # → http://localhost:8770
```

## 说明

- 下载配置（Cookie、Referer、Origin 等 HTTP headers）通过环境变量传入，详见 `download.sh` 顶部注释。
- 前端配置（Telegram Bot Token 等）见 `webapp/TELEGRAM.md`，存储在 `~/.config/anime-notify.env`。
- `urls.txt` 为下载列表示例，格式：`名称$URL`。

## 安装依赖

```bash
# Python
pip install fastapi uvicorn

# N_m3u8DL-RE（自行安装）
# https://github.com/nilaoda/N_m3u8DL-RE
```

## 原仓库使用说明（原版 README）

基于 FastAPI 的本地 Web 前端：粘贴 m3u8 链接 → 批量下载 → 实时进度条 + 磁盘/文件视图。
后端调用 `../download.sh`（Linux 版 N_m3u8DL-RE + ffmpeg 混流），无需 Windows。

## 并发 / 提速

两种情况要分开：

| 手段 | 做法 | 实测 |
|---|---|---|
| **单集多线程**（关键）| `THREADS=16`（默认）→ NRE `--thread-count 16` | `tc=1` 单集 **199s** → `tc=16` **6s**（同一 98MB 集）|
| **多集并发**（可选）| `./download_par.sh 3`，把列表分 3 片并行 | 3 集并发各 26s、总 26s（对比顺序 588s）|

**最重要的一条**：`--thread-count 1` 会让分片**串行**下载（每片一次往返延迟），是最大瓶颈。
默认已从 1 调到 16。

- 修改单集线程数：`THREADS=8 ./download.sh`
- 多集并发分片：`JOBS=3 ./download_par.sh`（内部给每片设 `SHARD=k/N`，靠 SKIP 去重，不重不漏）
- 注意 CDN 速率波动大（实测 4–17MB/s），过高的线程数不一定更快。

## 死链（CDN 上不存在）

`urls.txt` 的 291 条里，**18 条是 404**（CDN 根本没有该 m3u8），永远下不到：

- EP105、EP106
- EP219–EP231（连续 13 集）
- EP256、EP257、EP260

所以**实际可下上限是 273 集**。这 18 条已写入 `../dead.txt`，`download.sh` 会自动 `SKIP (known-404)`，不再浪费重试时间。

重新体检全部链接：`python3 /tmp/check.py`（会顺带刷新 `dead.txt`）。

## 启动

```bash
cd ~/workspace/anime/webapp
./run.sh                      # → http://localhost:8770
# 或指定端口：
PORT=9000 ./run.sh
```

后台常驻（推荐用 systemd 用户服务，掉线自动重启、登出后仍运行）：

```bash
systemctl --user status  anime-webapp   # 状态
systemctl --user restart anime-webapp   # 重启
systemctl --user stop    anime-webapp   # 停止
journalctl --user -u anime-webapp -f    # 日志（另见 webapp.log）
```

服务单元：`~/.config/systemd/user/anime-webapp.service`（`/usr/bin/python3 app.py`，`Restart=always`，`Linger=yes`）。

下载任务同样由 systemd 托管：`systemctl --user {status,restart,stop} anime-download`。

### 正确停止下载（避免僵尸进程）

**只用 `systemctl --user stop/restart anime-download`**，不要 `kill -9` 脚本进程：
- `KillMode=mixed` + `KillSignal=SIGTERM`：先给主进程发 TERM，脚本 trap 会 `kill` 并 `wait` 回收 NRE 再退出；
- `TimeoutStopSec=20` 后才对 cgroup 兜底 SIGKILL；
- 脚本内 `flock` 单实例锁：重复启动会被拒绝（重复实例是孤儿/僵尸的主要来源）；
- 手动兜底：`systemctl --user kill -s TERM anime-download`（按 cgroup 杀，不产生孤儿）。

Windows 浏览器访问 **http://localhost:8770**（WSL2 端口转发）；
若不通，用 WSL IP：`http://$(hostname -I | awk '{print $1}'):8770`。

> 注意：不要用 8765 端口（与 Hermes 自身 WebUI 冲突）。

## 使用

1. 在左侧文本框**粘贴链接**（每行一条）。支持两种格式：
   - `名称$URL`（你现有的 `urls.txt` 格式）
   - 纯 `URL`（自动命名，如 `我們這一家 - EP7`）
2. 点「保存到 urls.txt」，再点「开始下载」。
3. 右侧实时显示：总进度条、当前集进度条、任务明细、挂载点容量、已下载文件。

> 输出目录不存在会**自动创建**（含多级）。改完目录按回车/点空白即建，标签旁显示「✓ 已自动创建 / ✓ 已存在」；创建失败会红字提示原因。

> `download.sh` 只识别 `名称$URL` 行；纯 URL 会在保存时自动补上名称。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 页面 |
| GET | `/api/state` | 运行状态/进度/磁盘/文件 |
| GET | `/api/urls_text` | 读取 urls.txt |
| POST | `/api/urls` | 保存链接列表 `{text}` |
| POST | `/api/start` | 启动下载 `{outdir,start,count}` |
| POST | `/api/mkdir` | 按 `{outdir}` 自动创建目录（不存在则建，含多级）|
| POST | `/api/stop` | 停止下载 |
| GET | `/api/notify` | 通知开关状态 `{configured,chat_id_set,enabled}` |
| POST | `/api/notify` | 切换通知开关 `{enabled}` |
| POST | `/api/notify_test` | 发送测试通知（开关关闭时不发送） |
| GET | `/api/log?tail=120` | 日志尾部 |

## 通知开关

前端「🔔 通知：开/关」按钮一键静默 Telegram 通知，状态写入 `~/.config/anime-notify.env` 的
`NOTIFY_ENABLED`（默认开）。关闭后 `notify.sh` 跳过所有通知，下载服务不受影响。详见 `TELEGRAM.md`。

## 说明

- 前端默认输出目录：`/mnt/z4pro/video/儿童/我们这一家`（NAS，Z4Pro 共享）。
- 前端日志写到 `../_web.log`（独立于全量任务的 `_download.log`），启动时清空。
- 若检测到已有 `download.sh` 在跑，「开始下载」会返回 409（避免并发）。
