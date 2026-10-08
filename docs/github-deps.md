# npm / pnpm 安装 GitHub 依赖（本机可用做法）

本机 **github.com 无法直连**，git 已把 github.com 请求重写到 `ghproxy.net` 镜像。
但 `url.insteadOf` **只对 git 自己发起的请求生效**，所以不同依赖形态结果不同。

## 各形态实测结果

> ⚠️ 前提：`git` 必须在 PATH 上。本机 `D:\Git\cmd` 已配好，**新开终端**即可；
> DSH 客户端自身要**重启一次**才会继承新 PATH —— 否则它调用的 pnpm 会报找不到 git。

| 依赖形态 | 示例 | 本机可用性 |
|---|---|---|
| `github:` / `owner/repo#ref` / `git+https://github.com/...` | `npm i github:user/repo#v1.2.3` | ✅ 走 git，镜像重写自动生效（**npm 11.20 与 pnpm 11.7 均已实测装成功**） |
| `https://codeload.github.com/...tar.gz` | `"dep": "https://codeload.github.com/user/repo/tar.gz/v1.2.3"` | ❌ 直连不通，镜像对该路径返回 403 |
| `https://github.com/.../archive/...tar.gz` | | ⚠️ 直连不通，需加镜像前缀或先下载成本地文件 |
| `git+ssh://git@github.com/...` | | ❌ SSH 到 github.com 不通；私有仓库需真正的代理/VPN |

## 推荐做法

1. **优先用 git 形态**：
   ```powershell
   npm i github:owner/repo#v1.2.3
   ```
2. **必须用 tarball 时，先取到本地再装**（不再依赖镜像可用性，工程也可移植）：
   ```powershell
   ghpkg owner/repo v1.2.3                      # 存到 .\vendor\ 下
   npm i .\vendor\repo-v1.2.3.tar.gz
   ```
   package.json 里则写：`"dep": "file:vendor/repo-v1.2.3.tar.gz"`
3. **不要**在 package.json 里写 `codeload.github.com` 直链。

## 相关命令

| 命令 | 作用 |
|---|---|
| `ghdl <github-url> [输出文件]` | 经镜像下载任意 GitHub 地址；codeload 的 zip/tar.gz 自动改写成 archive 形式 |
| `ghpkg <owner/repo> [tag或分支] [输出目录]` | 经镜像取仓库快照到 `vendor/`（先试 tag，再试分支），并打印可直接执行的安装命令 |

