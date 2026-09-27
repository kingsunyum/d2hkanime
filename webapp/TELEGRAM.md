## Telegram 通知

支持**完成 / 失败 / 异常退出 / 服务崩溃**四类通知。未配置时全部静默跳过。

### 配置（token 只写本地文件，勿发聊天）

```bash
vi ~/.config/anime-notify.env     # 已创建，权限 600
```

填两项：

```
TELEGRAM_BOT_TOKEN=123456:ABC...        # @BotFather → /newbot
TELEGRAM_CHAT_ID=123456789              # 给 bot 发条消息后，看
                                        # https://api.telegram.org/bot<TOKEN>/getUpdates
```

可选代理（直连不通时才需要）：

```
TELEGRAM_PROXY=http://127.0.0.1:7890
```

## 通知开关（一键静默）

不想收通知时不用清空 token，改一个开关即可：

```
NOTIFY_ENABLED=0        # 0/false/no/off 关闭；1 或留空开启（默认开）
```

- 前端左上「🔔 通知：开/关」按钮可直接切换（写回 `~/.config/anime-notify.env`，权限保持 600）。
- 关闭后 `notify.sh` **静默跳过一切通知**（下载开始/失败/完成、单元失败通知都包含），「测试通知」也不会发送。
- 适合场景：**已停止下载服务 / 重启 WSL 时不想再被打扰**。下载与前端服务本身不受影响。

改完点前端「测试通知」验证。

## 触发点

| 事件 | 消息 |
|---|---|
| 开始下载 | `⏬ 开始下载` + 列表/目录/时间 |
| 单集失败 | `❌ 下载失败` + 条目/rc（前 10 条逐条，之后汇总） |
| 正常结束 | `🎬 动画下载完成`（有失败则 `⚠️ 动画下载结束（有失败）`）+ ok/fail/耗时 |
| script 非正常退出 | `❌ 下载异常退出（rc=N）`（手动 `systemctl stop` 不报） |
| systemd 单元失败 | `❌ systemd 单元异常: <unit>`（`OnFailure=` 模板单元） |

### 相关文件

- `~/workspace/anime/notify.sh` — 发送器
- `~/.config/anime-notify.env` — 配置（600）
- `~/.config/systemd/user/anime-fail-notify@.service` — 服务级失败通知模板
- 手动发：`~/workspace/anime/notify.sh "内容"`
