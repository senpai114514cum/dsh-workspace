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

## GitHub 访问（直连优先，镜像兜底）

- **当前状态**：VPN 已开启，github.com **直连可用**（已实测 clone / ls-remote / 下载），全局 git 重写规则已撤下——请求走真站，推送与凭据都正常。
- **VPN 关闭时**：运行 `gh-mirror-on` 把 5 条重写规则加回来（github.com → ghproxy.net）；恢复 VPN 后运行 `gh-mirror-off` 撤下。
- **下载命令**：`ghdl` 默认直连，失败会自动回退镜像；`ghdl -m <url>` 强制走镜像。`ghpkg` 同理（取仓库快照到 `vendor/`）。
- 镜像只用于**读取公开内容**：不要经它推送，私有仓库的凭据不要经它。
- `api.github.com` 始终直连。

## 相关文档

- [npm / pnpm 安装 GitHub 依赖](docs/github-deps.md)

