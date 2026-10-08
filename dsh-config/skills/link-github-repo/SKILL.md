---
name: link-github-repo
description: 在国内网络环境下获取 GitHub 开源仓库：判定是否挂了 VPN，直连优先，失败自动回退 ghproxy.net 镜像或 Gitee 镜像；含 clone、单文件下载、作为 npm 依赖、以及只读边界。当任务需要克隆、拉取、下载 GitHub 仓库或把 GitHub 仓库作为项目依赖时加载。
whenToUse: 需要 clone / 拉取 / 下载 GitHub 仓库，或把 GitHub 仓库作为依赖、或 GitHub 直连失败需要替代路线时。
---

# 获取 GitHub 仓库（直连优先，镜像兜底）

## 一、先判定网络

```powershell
git ls-remote --exit-code https://github.com/<owner>/<repo>.git HEAD   # 退出码 0 = 直连可用
Test-NetConnection 127.0.0.1 -Port 7890                               # True = 本机代理（VPN 客户端）在跑
```

## 二、按判定选路线

| 情况 | 做法 |
|---|---|
| 直连可用 | `git clone https://github.com/<owner>/<repo>.git`（git 已配好经代理 7890） |
| 直连不可用 | `ghclone <owner/repo> [目标目录] [分支或标签]` —— 自动 直连 → 镜像 → Gitee 依次尝试并报告结果 |
| 只想下一个文件 / 发布包 | `ghdl <github-url> [输出文件]`；强制镜像加 `-m` |
| 作为 npm 依赖 | `ghpkg <owner/repo> <tag>` 后用 `npm i .\vendor\*.tar.gz`；或 `npm i github:owner/repo#tag` |
| 只想探测哪条路通 | `ghclone <owner/repo> -NoClone`（可用 `-Force direct|mirror|gitee` 指定单条） |

## 三、命令清单（均在 D:\Tools\bin，已加入 PATH）

- `ghclone <owner/repo> [目录] [ref] [-Force …] [-NoClone]`：智能克隆，自动回退
- `ghdl [-m] <github-url> [输出文件]`：下载；默认直连、失败回退镜像
- `ghpkg <owner/repo> [tag或分支] [输出目录]`：取仓库快照到 `vendor/`，并打印安装命令
- `gh-proxy-on` / `gh-proxy-off`：本机代理（git 与 HTTP(S)_PROXY）开关
- `gh-mirror-on` / `gh-mirror-off`：git 的 5 条 GitHub→ghproxy.net 重写规则开关

## 四、边界与常见坑

- 镜像**只能读公开内容**：不要经镜像推送，私有仓库凭据不要经镜像。
- 镜像对 `codeload.github.com` 返回 403：仓库快照用 `ghpkg`（自动改写为 `github.com/.../archive/...`）或 `git clone`。
- `api.github.com` 一直直连可用。
- 报 “git 不是内部或外部命令”：`D:\Git\cmd` 不在 PATH（DSH 客户端需重启一次才会继承新 PATH）。
- 报 “Failed to connect … over proxy 127.0.0.1”：VPN 关了但 git 仍配着代理 → `gh-proxy-off`（或 `ghclone` 会自动跳过该路线）。
- 直连与镜像都失败：先查 VPN 与代理端口（`gh-proxy-on` 里的 7890 需按实际改），再考虑 Gitee 上的同名镜像仓库。
