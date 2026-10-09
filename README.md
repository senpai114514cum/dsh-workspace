# DSH 工作区

DeepSeek Harness（桌面端）的默认工作区，用于放置日常任务产生的文件与项目。

## 项目

| 目录 | 说明 |
|---|---|
| [`projects/mineru-docparse`](projects/mineru-docparse) | MinerU 文档解析流水线：批量 PDF→Markdown 的图形界面工具 + 幻觉检测/自动清理 + 5 份实测报告 |

## 本机环境备忘

| 组件 | 位置 / 版本 |
|---|---|
| Git | `D:\Git`，2.56.0.windows.2（用户 PATH 含 `D:\Git\cmd`） |
| Node.js | `D:\Node`，v26.11.1（npm 11.20.0） |
| npm 源 | `https://registry.npmmirror.com/`（`~/.npmrc`） |
| GitHub 读取 | 经 `ghproxy.net` 镜像（`~/.gitconfig` 的 `url.insteadOf`） |
| SSH 密钥 | Gitee：`~/.ssh/id_ed25519`；GitHub：`~/.ssh/id_ed25519_github`（均无口令） |
| DSH 插件 | `dsh-whale-widget` 0.3.18（desktop profile） |

## 注意

- 不要把 `~/.dsh` 直接做成 git 仓库：里面有 `.credentials.yaml` 等凭据。
- `.gitignore` 已排除运行时数据与本地凭据类文件。

## GitHub 访问（代理优先，镜像兜底）

- **VPN 开启时（当前状态）**：git 与 curl 走本机代理 `http://127.0.0.1:7890`；`gitee.com`、`registry.npmmirror.com` 等国内域名已通过 `NO_PROXY` 与 git 的 URL 级设置**豁免代理**，保持直连。
- **VPN 关闭时**：先运行 `gh-proxy-off`（撤掉 git/环境变量里的代理，否则连 github 会报连接被拒）；需要读 GitHub 公开内容再运行 `gh-mirror-on` 走镜像，用完 `gh-mirror-off`。
- **下载命令**：`ghdl` 默认经代理直连，失败自动回退镜像；`ghdl -m <url>` 强制镜像。`ghpkg` 同理（取仓库快照到 `vendor/`）。
- 镜像只用于**读取公开内容**：不要经它推送，私有仓库的凭据不要经它。

| 开关命令 | 作用 |
|---|---|
| `gh-proxy-on` / `gh-proxy-off` | 切换 git 与 HTTP(S)_PROXY 环境变量的本机代理 |
| `gh-mirror-on` / `gh-mirror-off` | 切换 git 的 5 条 GitHub→ghproxy.net 重写规则 |

## 相关文档

- [npm / pnpm 安装 GitHub 依赖](docs/github-deps.md)

> 若弹出 Git Credential Manager 窗口（只有访问**需要登录的 HTTPS 仓库**时才会弹，`.ssh` 走 SSH 不会弹），点 Cancel 即可；本仓库与 Gitee 都走 SSH，日常不会遇到。

## 远端与推送

| 远端 | 地址 | 说明 |
|---|---|---|
| `origin` | `git@gitee.com:ninjia400/dsh-workspace.git` | Gitee，**主远端**（国内直连，不需要 VPN） |
| `github` | `git@github.com:senpai114514cum/dsh-workspace.git` | GitHub，备用/分享（SSH 走 443 通道，需要 VPN） |

```powershell
git push                 # 推 Gitee（当前分支跟踪 origin/main）
git push github main     # 推 GitHub
git pull                 # 从 Gitee 拉
```

- 两个平台各有独立 SSH 密钥：Gitee 用 `~/.ssh/id_ed25519`，GitHub 用 `~/.ssh/id_ed25519_github`。
- 配置见 `~/.ssh/config`：GitHub 默认走 `ssh.github.com:443`，需要时可用 `github-22` 走 22 端口。

## DSH 全局约定与技能（跨会话生效）

本机有两处"所有会话都生效"的配置，源文件也版本化在本仓库 `dsh-config/` 下：

| 位置 | 作用 |
|---|---|
| `~/.dsh/AGENTS.md` | **用户级全局指令**，DSH 会把它注入每个会话的上下文 |
| `~/.dsh/skills/link-github-repo/SKILL.md` | 技能目录（DSH 监听该目录，新增技能无需重启即进入所有会话的技能目录） |

策略：**挂 VPN 时直连 GitHub；未挂 VPN 时自动回退 ghproxy.net 镜像或 Gitee 镜像**；镜像仅用于读取公开内容。
一条命令即可完成判定与回退：`ghclone <owner/repo> [目录]`。

在另一台机器上重建这套配置：`pwsh -File .\dsh-config\install.ps1`

