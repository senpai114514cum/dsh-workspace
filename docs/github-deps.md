# npm / pnpm 安装 GitHub 依赖（本机做法）

本机网络有两种状态：**挂 VPN 时 github.com 可直连**；不挂时走 `ghproxy.net` 镜像（由 `gh-mirror-on` / `gh-mirror-off` 切换 git 重写规则）。
注意 `url.insteadOf` **只对 git 自己发起的请求生效**，所以不同依赖形态结果不同。

## 两种状态下的可用性

| 依赖形态 | 示例 | VPN 开启 | VPN 关闭（镜像） |
|---|---|---|---|
| `github:` / `owner/repo#ref` / `git+https://github.com/...` | `npm i github:user/repo#v1.2.3` | ✅ 直连（npm 与 pnpm 均已实测装上 0.3.18） | ✅ 走镜像重写 |
| ``https://codeload.github.com/...`` | ``"dep": "https://codeload.github.com/user/repo/tar.gz/v1.2.3"`` | ✅ VPN 开启时直连可用（已实测） |
| `https://github.com/.../archive/...tar.gz` | | ✅ 直连 | ⚠️ 需镜像前缀或本地文件 |
| `git+ssh://git@github.com/...` | | ⚠️ 需在 GitHub 登记 SSH 公钥 | ❌ 镜像不转发凭据 |

## 推荐做法

1. **优先用 git 形态**：`npm i github:owner/repo#v1.2.3`
2. **需要 tarball 时先取到本地**（两种网络状态下都能装）：
   ```powershell
   ghpkg owner/repo v1.2.3
   npm i .\vendor\repo-v1.2.3.tar.gz
   ```
   package.json 里写：`"dep": "file:vendor/repo-v1.2.3.tar.gz"`
3. `git` 必须在 PATH 上（本机 `D:\Git\cmd` 已配好；DSH 客户端需重启一次才会继承）。

## 相关命令

| 命令 | 作用 |
|---|---|
| `ghdl [-m] <github-url> [输出文件]` | 下载 GitHub 地址；默认直连，失败回退镜像，`-m` 强制镜像 |
| `ghpkg <owner/repo> [tag或分支] [输出目录]` | 取仓库快照到 `vendor/`（先试 tag 再试分支），打印安装命令 |
| `gh-mirror-on` / `gh-mirror-off` | 切换 git 的 5 条 GitHub→镜像重写规则 |
