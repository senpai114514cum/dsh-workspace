# DSH 工作区

DeepSeek Harness（桌面端）的默认工作区，用于放置日常任务产生的文件与项目。

## 本机环境备忘

| 组件 | 位置 / 版本 |
|---|---|
| Git | `D:\Git`，2.56.0.windows.2（用户 PATH 含 `D:\Git\cmd`） |
| Node.js | `D:\Node`，v26.11.1（npm 11.20.0） |
| npm 源 | `https://registry.npmmirror.com/`（`~/.npmrc`） |
| GitHub 读取 | 经 `ghproxy.net` 镜像（`~/.gitconfig` 的 `url.insteadOf`） |
| Gitee | SSH 密钥 `~/.ssh/id_ed25519`（无口令） |
| DSH 插件 | `dsh-whale-widget` 0.3.18（desktop profile） |

## 注意

- 不要把 `~/.dsh` 直接做成 git 仓库：里面有 `.credentials.yaml` 等凭据。
- `.gitignore` 已排除运行时数据与本地凭据类文件。
