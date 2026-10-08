# npm / pnpm 安装 GitHub 依赖（本机做法）

本机 github.com 需要经**本机代理**（`http://127.0.0.1:7890`，VPN 客户端提供）；
不挂 VPN 时改走 `ghproxy.net` 镜像（`gh-mirror-on` / `gh-mirror-off` 切换）。
注意 `url.insteadOf` **只对 git 自己发起的请求生效**，所以不同依赖形态结果不同。

## 各形态实测结果

| 依赖形态 | 示例 | 结果 |
|---|---|---|
| `github:` / `owner/repo#ref` / `git+https://github.com/...` | `npm i github:user/repo#v1.2.3` | ✅ 走 git（经代理）；npm 11.20 与 pnpm 11.7 均已实测装上 0.3.18 |
| `https://codeload.github.com/...` | `"dep": "https://codeload.github.com/user/repo/tar.gz/v1.2.3"` | ✅ 经代理直连可用（实测 200）；不挂 VPN 时该路径镜像返回 403 |
| `https://github.com/.../archive/...tar.gz` | | ✅ 经代理直连；不挂 VPN 时需镜像前缀或本地文件 |
| `git+ssh://git@github.com/...` | | ⚠️ SSH 链路已通（22 端口可达），但需先在 GitHub 登记 SSH 公钥；不挂 VPN 时不可用 |

## 推荐做法

1. **优先用 git 形态**：`npm i github:owner/repo#v1.2.3`
2. **需要 tarball 时先取到本地**（两种网络状态都能装）：
   ```powershell
   ghpkg owner/repo v1.2.3
   npm i .\vendor\repo-v1.2.3.tar.gz
   ```
   package.json 里写：`"dep": "file:vendor/repo-v1.2.3.tar.gz"`
3. `git` 必须在 PATH 上（本机 `D:\Git\cmd` 已配好；DSH 客户端需重启一次才会继承）。

## 相关命令

| 命令 | 作用 |
|---|---|
| `ghdl [-m] <github-url> [输出文件]` | 默认直连（经代理），失败回退镜像；`-m` 强制镜像 |
| `ghpkg <owner/repo> [tag或分支] [输出目录]` | 取仓库快照到 `vendor/`，打印安装命令 |
| `gh-proxy-on` / `gh-proxy-off` | 切换本机代理（git + HTTP(S)_PROXY） |
| `gh-mirror-on` / `gh-mirror-off` | 切换 GitHub→镜像 重写规则（无 VPN 时用） |

## 代理相关（当前机制）

- git 全局配了 `http.proxy` / `https.proxy` = `http://127.0.0.1:7890`，并用 `http.https://gitee.com.proxy`（空值）**豁免 gitee**（已用"坏代理"差异测试验证）。
- 用户环境变量 `HTTP_PROXY` / `HTTPS_PROXY` 指向同一代理，`NO_PROXY` 含 `gitee.com,registry.npmmirror.com,registry.npmjs.org,localhost,127.0.0.1,::1`。
- npm 的 proxy 已删除（它只与国内 registry 通信）。
- 开关：`gh-proxy-on` / `gh-proxy-off`（代理）、`gh-mirror-on` / `gh-mirror-off`（无 VPN 时走镜像）。
- 访问需要登录的 HTTPS GitHub/Gitee 仓库时，Git Credential Manager 可能弹窗；本工作流用 SSH 与令牌，点 Cancel 即可。

