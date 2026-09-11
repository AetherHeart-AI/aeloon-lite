# 网页与远程 Desktop 部署

[English](remote-deployment.md) | 简体中文

一台 Runtime 为受信任团队提供浏览器工作台和远程 Desktop。用户有独立账号与应用数据归属，
执行仍使用共享系统账号；不提供恶意用户之间的 Shell 隔离承诺。沙箱默认开启，Linux 需要
Bubblewrap 和用户命名空间；不能启动沙箱时不自动绕过。

## 安装兼容的一组产物

Linux ARM64 或 x86_64，需要 `curl`、`tar`、`jq`、`sha256sum`。生产服务无需 Node、Bun 或 Vite。

```sh
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sh
```

安装器从稳定版的同一 Release 下载 Runtime 与 `aeloon-client-<Desktop版本>.tar.gz`，校验 GitHub
Release 摘要，在 `~/.local/share/aeloon-runtime/releases/<Release标签>` 成组安装。服务器托管的
`client` 与 Desktop 打包的 `dist/client` 是同一次构建。安装器不启动服务，也不改旧数据。

## 准备地址、证书与新数据目录

IP 和域名均可。证书 SAN 必须覆盖用户访问的地址，完整证书链必须被浏览器和 Desktop 信任：
使用公网可信证书，或在所有客户端预装内网 CA。没有自签证书开箱即用、指纹信任或忽略 TLS
校验的入口。证书签发、续期、替换，以及替换后的服务重启由部署工具维护。

主机防火墙与云安全组放行所选 TCP 端口，默认 `7420`。首次远程部署必须指定全新 `--data-dir`；
旧目录会被明确拒绝，不能通过 reset 或自动迁移继续使用。旧服务、安装树与数据独立保留；测试
必须使用独立目录、端口和服务名。此要求不升级 Desktop 本地数据版本，也不要求本地数据重置。

```sh
aeloon-runtime-server account init --data-dir ~/.aeloon-server-accounts
```

CLI 交互输入首位管理员的用户名与密码；密码至少 12 个字符，不使用命令参数。无启用管理员时
拒绝启动远程服务。随后运行：

```sh
aeloon-runtime-server run --host runtime.example.com --bind 0.0.0.0 --port 7420 \
  --data-dir ~/.aeloon-server-accounts \
  --client-dir ~/.local/share/aeloon-runtime/current/client \
  --tls-cert /path/to/fullchain.pem --tls-key /path/to/privkey.pem
```

浏览器打开 `https://runtime.example.com:7420/`；Desktop 选择远程登录，填写相同服务器地址、
用户名和密码。浏览器支持 `/`、`/login`、`/admin` 的直接访问与刷新。Desktop 本地模式和多连接
保持可用；远程会话由主进程保存在用户私有文件中，不保存密码、不传会话令牌给渲染层。

## 账号与管理员配置

没有开放注册。管理员在 `/admin` 创建用户、修改资料与角色、重置密码、停用或启用账号；
停用保留数据，最后一位启用管理员不能被停用或降级。用户可以修改自己的密码。管理员不因此
获得查看他人私有内容的入口。Provider、云账号、搜索密钥、默认模型和全局工具由管理员管理；
普通用户选择开放模型，个人 Skill、Agent 与会话偏好仍属于本人，群聊遵守成员可见性。

会话在连续 30 天未使用后过期。活跃客户端通过认证接口续期，网络心跳不续期。退出撤销当前
会话；改密、密码重置、停用和角色变化撤销全部会话并关闭连接。忘记密码时在服务器执行：

```sh
aeloon-runtime-server account reset-password --data-dir ~/.aeloon-server-accounts
```

远程关闭 Shell 沙箱只有管理员可操作，关闭后 Shell 使用共享系统账号权限。开启沙箱也不扩大
团队信任边界。HTTPS、监听、端口和启停只能通过 CLI、服务管理器与部署工具维护。

## 服务管理与升级

创建一个新的 systemd 用户单元，使用上面的完整命令作为 `ExecStart`，设 `Type=simple`、
`Restart=on-failure`。为避免安装新版本影响原服务，生产单元使用已验收的 `releases/<标签>`
绝对路径，同时固定该目录下的 `client`。读取证书私钥所需的权限由服务器管理员配置。

升级先在独立目录和端口验证新的一组 Runtime、网页和 Desktop，再由部署负责人显式切换。
发布不会自动升级或切换现有部署。不得混用不同协议版本；不兼容客户端明确要求更新。旧配对
凭据与系统凭据库不读取、不迁移、不删除，需要时重新登录。

## 文件与排障

上传保留原附件协议与大小限制。附件和产物通过认证 HTTP 流式下载；图片、文本和 PDF 可预览，
HTML、SVG 等主动内容强制下载。文件管理器入口仅限 Desktop。关闭浏览器不终止服务器 Agent。

证书错误先检查访问地址、SAN、有效期和客户端信任；连接超时检查服务监听、主机防火墙和云
安全组；账号失效重新登录；无管理员先执行交互初始化。不要通过放宽 TLS、复制旧凭据或重置
旧数据来绕过这些错误。
