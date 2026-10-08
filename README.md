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

## GitHub 镜像用法（本机 github.com 不可直连）

- **git 操作**（clone / fetch）：已配 `url.insteadOf`，直接写 github.com 地址即可，自动走 `ghproxy.net` 镜像。
- **下载 raw / codeload / release 资产**：在 URL 前加 `https://ghproxy.net/`，或直接用装好的 `ghdl` 命令：

  ```powershell
  ghdl https://raw.githubusercontent.com/user/repo/main/file.json file.json
  ghdl https://github.com/user/repo/releases/download/v1/app.zip
  curl.exe -L -o out.zip "https://ghproxy.net/https://codeload.github.com/user/repo/zip/refs/heads/main"
  ```

- `api.github.com` 保持直连（本机可达，未被替换）。
- 镜像仅用于**读取公开内容**：不要经它推送，私有仓库的凭据不要经它。
