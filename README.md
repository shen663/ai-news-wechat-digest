# 每日 AI 热点微信简报

每天北京时间 10:00 运行一次：读取国内与全球 AI 资讯，合并重复报道，挑选最多 5 件事，生成中文摘要，并通过 Server酱 Turbo 发到个人微信。正常情况下优先保留国内、全球各 2 件，第 5 件按热度估计选择。

## 1. 准备密钥

需要 Python 3.10+、能访问这些新闻源与 API 的运行环境，以及两个密钥：

1. 在 [Server酱 Turbo](https://sct.ftqq.com/docs/getting-started/sendkey/) 用微信扫码登录，取得以 `SCT` 开头的 SendKey，并按控制台指引启用微信服务号通道。
2. 配置 `DEEPSEEK_API_KEY` 环境变量，用于选稿与生成中文摘要。接口格式见 [DeepSeek Responses API 文档](https://api-docs.deepseek.com/api/create-response/)。
3. 把 `.env.example` 复制为 `.env`，填入密钥。`.env` 已在 `.gitignore` 中；不要把密钥发到聊天里或提交到仓库。

PowerShell 示例：

```powershell
Copy-Item .env.example .env
notepad .env
```

如果 `DEEPSEEK_API_KEY` 已在电脑环境变量中，无需在 `.env` 重复填写。`DEEPSEEK_MODEL` 默认是 `deepseek-flash`。

## 2. 本地验证

```powershell
python -m unittest discover -s tests -v
python ai_digest.py run --dry-run
python ai_digest.py test-push
python ai_digest.py run
```

`--dry-run` 只打印，不发微信；没有 DeepSeek Key 时显示原始标题和摘要供检查。`test-push` 会实际发送一条测试消息。`run` 会发送当天简报，同一天再次运行会跳过，避免重复推送。

微信服务号通知卡片只显示标题，点开后可看五条完整内容；这是通道本身的展示方式。Server酱免费额度目前是每天 5 条，本项目每天只发一条合集。[通道说明](https://sct.ftqq.com/docs/getting-started/channels/)

## 3. 每天 10:00 自动运行

在 Windows 上，可以运行下面的脚本注册定时任务（它会检查系统时区是否为北京时间）：

```powershell
./install_schedule.ps1
```

你也可以在“任务计划程序”里手动创建每日任务：

| 设置 | 值 |
| --- | --- |
| 触发器 | 每天 10:00；计算机时区设为北京时间 |
| 程序 | `python.exe` 的完整路径；可用 `Get-Command python` 查看 |
| 参数 | `"<项目目录>\ai_digest.py" run` |
| 起始于 | `<项目目录>`（可运行 `Get-Location` 查看） |

上述 Windows 任务以交互登录会话运行：电脑需要在 10 点开机、联网且保持登录（锁屏可以）。若要不依赖个人电脑，应把同一项目放在持续运行的主机上，由该主机的定时任务在北京时间 10:00 执行 `python ai_digest.py run`。
运行日志保存在 `data/run.log`，当天推送记录保存在 `data/digest.sqlite3`。

## 工作原理与边界

- `sources.json` 配置信息源，目前包括 Google News 中文 AI、Bing News 中文 AI、量子位、TechCrunch AI、The Verge AI 和 Hacker News。RSS 源提供标题、时间及可能存在的摘要；Hacker News 还提供投票与评论数。Bing 新闻聚合链接会还原到原站；Google News 的链接通常会跳转到报道页面。
- 只选运行前 24 小时内的内容。热度是基于发布时间、跨来源出现次数、Hacker News 互动量的**估计值**，不是全网热搜排名。可以在 `sources.json` 增加有稳定 RSS 的来源。
- 国内/全球按标题中的事件主体估计，无法判断时沿用来源地区。模型会复核候选并写摘要；如果 AI 接口失败，正式运行会停止，不会发送未经检查的英文标题合集。
- 模型只拿到 RSS 标题与摘要，不会自动阅读全文。因此简报附原文链接，不能把摘要当作已经核对全文的报道。RSS 源无法访问或当天可靠候选不足时，会少发或停止，绝不补旧闻。
- `data/digest.sqlite3` 记录当天推送状态和最近已发事件。推送返回结果不明时状态设为 `uncertain`，不会自动重试，以免重复通知；可先在微信里确认是否收到，再人工处理。

代码入口是 [ai_digest.py](ai_digest.py)，信息源在 [sources.json](sources.json)，离线测试在 [tests/test_digest.py](tests/test_digest.py)。
