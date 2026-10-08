# 本机全局约定（所有会话适用）

## 获取 / 克隆 GitHub 开源仓库时的网络策略

本机在国内网络环境，`github.com` 是否可达取决于 VPN。**不要假设 GitHub 直连可用**，按下面顺序处理：

1. **先判定**（一条命令足够）：`git ls-remote --exit-code https://github.com/<owner>/<repo>.git HEAD` 退出码为 0 即直连可用。
2. **直连可用（挂了 VPN）** → 直接用 github.com 地址；git 已配置经本机代理 `127.0.0.1:7890` 访问。
3. **直连不可用（未挂 VPN）** → 按序回退：
   - 首选 `ghclone <owner/repo> [目标目录] [分支或标签]`：自动依次尝试 **直连 → ghproxy.net 镜像 → Gitee 镜像**，并报告实际用了哪条路。
   - 等价手工做法：`gh-mirror-on` 后正常 `git clone`，用完 `gh-mirror-off`。
   - 只下单个文件或发布包：`ghdl <github-url> [输出文件]`（默认直连、失败自动回退镜像；`-m` 强制镜像）。
   - 把 GitHub 仓库当 npm 依赖：`ghpkg <owner/repo> [tag]` 取到 `vendor/`，再 `npm i .\vendor\xxx.tar.gz`；或直接 `npm i github:owner/repo#tag`。
4. **只读边界**：镜像只能读取公开内容。**不要经镜像推送**，私有仓库凭据不要经镜像；需要推送时用 SSH（GitHub 用 `~/.ssh/id_ed25519_github`，Gitee 用 `~/.ssh/id_ed25519`）。
5. **不要**把 `codeload.github.com` 之类的 GitHub 直链写进项目的 package.json 当长期依赖（镜像对该路径返回 403）；用 `github:owner/repo#tag` 或本地 vendored 文件。
6. 网络状态切换用开关命令：`gh-proxy-on/off`（本机代理）、`gh-mirror-on/off`（GitHub→镜像重写）。

## 本机工具与路径

- Git：`D:\Git\cmd`（2.56）；Node/npm：`D:\Node`（v26 / npm 11，registry 为 npmmirror）。
- 自建命令在 `D:\Tools\bin`：`ghclone`、`ghdl`、`ghpkg`、`gh-proxy-on/off`、`gh-mirror-on/off`。
- 说明文档：https://gitee.com/ninjia400/dsh-workspace （README 与 `docs/github-deps.md`）。

## 安全约定

- 凭据类文件不要提交到 git、不要贴进对话：`~/.dsh/.credentials.yaml`、`~/.ssh/` 下的**私钥**、`*-public-key.txt` 已被 .gitignore 排除。
- DSH 插件安装方式二选一、不要混用：已用 npm 名安装的插件不要再改用 `github:` 规格重装。
