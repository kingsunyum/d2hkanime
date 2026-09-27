# d2hkanime

基于 [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) + ffmpeg 的 m3u8 批量下载工具集，含 FastAPI Web 前端。

## 功能

- `download.sh` — 批量下载，支持并发分片（多线程加速）
- `download_par.sh` — 并发多集下载
- `webapp/` — FastAPI Web 前端：粘贴 m3u8 链接 → 实时进度 → 磁盘/文件视图
- `notify.sh` — Telegram 通知（Bot Token / Chat ID 配置在 `~/.config/anime-notify.env`）
- `backfill_times.py` — 从日志回填下载时间戳

## 快速开始

```bash
# 1. 安装 N_m3u8DL-RE
# https://github.com/nilaoda/N_m3u8DL-RE/releases

# 2. 安装 Python 依赖
pip install fastapi uvicorn

# 3. 配置 Telegram（可选）
vi ~/.config/anime-notify.env
# TELEGRAM_BOT_TOKEN=xxx:yyy
# TELEGRAM_CHAT_ID=123456789

# 4. 批量下载（命令行）
./download.sh

# 5. Web 前端
cd webapp && ./run.sh  # → http://localhost:8770
```

## 配置

### HTTP Headers（下载脚本）

所有 HTTP headers 通过环境变量配置，详见 `download.sh` 顶部注释：

```bash
HTTP_COOKIE="your_cookie" \
HTTP_ORIGIN="https://www.example.com" \
HTTP_REFERER="https://www.example.com/" \
./download.sh
```

### urls.txt 格式

```
名称$URL
工作細胞 - EP01 肺炎鏈球菌$https://cdn.example.com/01.mp4/master.m3u8
```

### Web 前端

```
cd webapp && ./run.sh  # 默认端口 8770，PORT=9000 可改
```

## 目录结构

```
d2hkanime/
├── download.sh          # 批量下载主脚本
├── download_par.sh      # 并发分片下载
├── notify.sh            # Telegram 通知
├── backfill_times.py    # 下载时间戳回填
├── urls.txt             # 下载列表（示例）
├── dead.txt             # 已知死链
└── webapp/
    ├── app.py           # FastAPI 后端
    ├── index.html       # 前端页面
    ├── run.sh           # 启动脚本
    └── README.md        # 前端详细说明
```

## 隐私说明

- Telegram Bot Token、Chat ID 存储在 `~/.config/anime-notify.env`，已配置为 `chmod 600`
- Cookie 等 HTTP headers 通过环境变量传入，不在代码中硬编码
