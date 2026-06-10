# SVN 转 Git

将非标准分支结构(有分支概念但很混乱)的复杂 SVN 项目同步到 Git 仓库，并通过 Git Hook 拦截提交请求，自动将变更提交到 SVN 仓库

这样就能完全使用 Git 来提交/更新 SVN 仓库的代码啦！

[//]: # (公司还在用 SVN 进行代码版本管理，并且不是标准的 SVN 分支结构, 导致无法使用 SVN 原生的分支功能)
[//]: # (再加上我实在不喜欢 SVN 版本管理，所以想要把 SVN 仓库迁移到 Git 上，这样就可以使用 Git 的各种功能了)
[//]: # (但是没有找到能适用于我们项目的第三方同步工具，所以就只能自己写啦)

## 同步 SVN 提交记录到 Git

- [x] 定时同步
- [x] 接口调用同步
- [x] 邮件提醒(由于原 SVN 项目结构实在太复杂了，在提交未知模块、新建分支时需要人工核对和调整，我太难了...)
- [ ] Git 用户校验(个人暂无此需求，未来可能会加，GitLab 太重了，直接在本地用原生 Git 跑的，没有用户校验，有需要可以自行添加)

### Python 版本

当前项目是 Python 实现：读取 SVN 日志、按分支正则分组、生成 Git 提交，并支持 dry-run 检查同步计划。

本仓库规则要求先进入项目 Python 环境：

```shell
conda activate Svn2Git
```

离线验证配置和同步计划：

```shell
python -m svn2git validate-config --config config/application.yml
python -m svn2git sync --config config/application.yml --repo platform --log-xml tests/fixtures/svn_log.xml --dry-run
```

真实同步不传 `--dry-run`，也不传 `--log-xml` 时，会通过本机 `svn` 命令读取远程 SVN XML 日志，再执行后续 `svn update` / `git add` / `git commit` / `git push` 命令。

启动最小 HTTP 服务入口：

```shell
python -m svn2git serve --config config/application.yml --host 127.0.0.1 --port 8080
```

服务提供 `POST /sync/{repo}`、`POST /sync` 和 `GET /jobs/{repo}`，用于手动或外部定时任务触发同步并查询最近一次结果。当前实现使用 Python 标准库 HTTP server，不额外引入 Web 框架依赖。

### 配置

[application.yml.example](config%2Fapplication.yml.example) 是示例配置；实际使用时复制为 `config/application.yml` 并按本地环境修改。`config/application.yml` 已被 Git 忽略，不应提交账号、路径等本地正式配置。

#### SVN 账号

```yaml
svn:
  username: your_svn_username
  password: your_svn_password
```

#### 用户映射

我们的 SVN 中没有存用户的邮箱，但是 Git 必须有邮箱，所以这里配置了用户和邮箱映射

```yaml
git:
  user_map:
    user1name: user1email
    user2name: user2email
    user3name: user3email
```

#### 同步项目

```yaml
svn_git_mapping:
  platform:
    svn_url: your_svn_url
    svn_project_path: your_sync_svn_project_path
    git_project_path: your_sync_git_project_path
    dir_regx: a_regular_expression_to_match_your_project_branch
    full_sync_interval: 1000
  example:
    svn_url: http://127.0.0.1:8443/repo/example
    svn_project_path: F:\SvnRepo\SMPlatform
    git_project_path: F:\GitRepo\Platform
    dir_regx: .*/branches/([^/]+).*
```

由于项目结构复杂，不同的项目通过 `dir_regx` 正则表达式匹配分支...我太难了...

`full_sync_interval` 用来兜底修正增量同步可能产生的遗漏。程序会按 Git 分支独立记录上次全量同步的 SVN revision；当当前 revision 与该分支上次全量同步 revision 的差值大于等于配置值时，会先把本地 SVN 工作副本更新到当前 revision，再把该分支对应目录完整对账到 Git 分支并提交。全量同步成功后，只重置当前 Git 分支的计数。该配置默认是 `1000`，设为 `0` 可关闭全量兜底。

#### SVN 模块映射

如果多个 SVN 模块共同组成一个完整 Git 项目，可以在同一个顶层项目下配置 `modules`。这些模块会作为普通目录写入同一个 Git 工作树，不会创建 Git submodule、`.gitmodules` 或子模块指针提交。模块默认继承顶层项目的 `svn_url`、`dir_regx` 和 `dir_suffix`，也可以单独覆盖。

```yaml
svn_git_mapping:
  suite:
    svn_url: https://svn.example.com/repos/main
    svn_project_path: F:\SvnRepo\Suite
    git_project_path: F:\GitRepo\Suite
    git_remote_url: ssh://git.example.com/suite.git
    dir_regx: .*/branches/([^/]+).*
    modules:
      billing:
        svn_project_path: F:\SvnRepo\Billing
        target_path: modules/billing
        full_sync_interval: 500
        branch_overrides:
          dev:
            svn_url: https://svn.example.com/repos/billing-dev
            svn_project_path: F:\SvnRepo\BillingDev
      reporting:
        svn_project_path: F:\SvnRepo\Reporting
        target_path: modules/reporting
        dir_regx: .*/release/([^/]+).*
```

同步时会在顶层 Git 仓库中切换目标分支，分别更新参与本次 SVN revision 的模块工作副本，把文件复制到各自 `target_path` 下，然后按 Git 项目、Git 分支、SVN revision 提交一次。

模块未配置 `full_sync_interval` 时继承父仓库；单独配置后只影响该模块。全量同步状态写在 Git 工作树的 `.svn_full_sync_versions/<target>/<git_branch>` 下，普通增量 checkpoint 仍使用 `.svn_version` 或 `.svn_versions/<target>`。

如果同一个模块的不同分支来自不同 SVN 仓库或不同工作副本路径，可以使用 `branch_overrides` 指定分支级来源。上例中 `billing` 模块的 `dev` 分支会使用 `https://svn.example.com/repos/billing-dev` 和 `F:\SvnRepo\BillingDev`。真实同步默认会在提交后执行 `git push --all`；只想验证本地 Git 提交时加 `--no-push`。

Singularity 这类项目可以把 Common 和 framework 配成同一个 Git 项目下的两个 SVN 模块。两个模块都写入 Git 根目录，所以 `target_path` 使用 `.`；它们的实际文件目录由 SVN 变更路径和 `dir_suffix` 决定。

```yaml
svn_git_mapping:
  singularity:
    svn_url: https://192.168.0.182:8443/repo/codes/IOTP/Tobacco/trunk/Singularity
    svn_project_path: F:\SvnTest\Singularity
    git_project_path: F:\Svn2GitTest\Singularity
    modules:
      common:
        svn_url: https://192.168.0.182:8443/repo/codes/IOTP/Tobacco/trunk/Singularity/Common
        svn_project_path: F:\SvnTest\SingularityCommon
        target_path: .
        dir_regx: .*/Common/([^/]+)/common/.*
        branch_overrides:
          "2.13":
            svn_url: https://192.168.0.182:8443/repo/codes/SafeMg/Singularity/Common/2.13/common
            svn_project_path: F:\SvnTest\SingularityCommon-2.13
            dir_suffix: common
      framework:
        svn_url: https://192.168.0.182:8443/repo/codes/IOTP/Tobacco/branches/Singularity
        svn_project_path: F:\SvnTest\SingularityFramework
        target_path: .
        dir_regx: .*/branches/Singularity/([^/]+)/framework/.*
        branch_overrides:
          platform_2.13:
            svn_url: https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches/platform_2.13
            svn_project_path: F:\SvnTest\SingularityFramework-2.13
            dir_regx: .*/branches/([^/]+)/.*
            branch_name: "2.13"
```

Common 默认分支来自 `.../IOTP/Tobacco/trunk/Singularity/Common/{分支名}/common`，`2.13` 分支单独覆盖到 `.../SafeMg/Singularity/Common/2.13/common`，Git 分支仍是 `2.13`。framework 默认分支来自 `.../IOTP/Tobacco/branches/Singularity/{分支名}/framework`，但 `2.13` 的 SVN 源分支名是 `platform_2.13`，因此覆盖项 key 使用 `platform_2.13`，再通过 `branch_name: "2.13"` 写入 Git 的 `2.13` 分支。

#### 邮件提醒

原因上面说了...我太难了...

```yaml
mail:
  sender: your_email_address
  recipient: your_recipient_email_address
  password: your_password
  host: stmp.qq.com
```

### Git 项目中的配置

运行过程中，每次同步提交记录都会从 master 分支检出以下文件到当前分支中

即：以下文件永远以 master 分支为准，有变动需要在 master 分支提交

- hooks 目录: 钩子脚本放这里
  - pre-commit: Git Hook 脚本，用于拦截提交请求，将变更提交到 SVN 仓库
  - pre-push: 禁止 Push(服务端也要禁止)
- .gitignore
- config.bat: 用于一键配置客户端钩子
- config.sh: 同上
- README.md: 项目说明，客户端自动提交到 SVN 需要配置，有说明最好
- svn_git_map.properties(可选): 用来配置极其复杂的项目的模块映射

#### config.bat

```shell
XCOPY /Y hooks\* .git\hooks\
```

#### config.sh

```shell
cp hooks/* .git/hooks/
```

## 自动提交到 SVN

当前支持的反向同步模式是兼容模式：客户端 Git Hook 不再读取 `.svn_path`，也不再修改开发者本地 SVN 工作副本。Hook 会把分支、提交信息和变更文件列表发送给服务的 `POST /reverse-sync/{repo}`，由服务自有目录负责后续 Git-to-SVN 处理。

客户端安装 `hooks/Platform` 或 `hooks/Singularity` 下的 `pre-commit` / `pre-push` 后，需要配置：

```shell
export SVN2GIT_SERVICE_URL=http://127.0.0.1:8080
export SVN2GIT_REPO_NAME=Platform
```

Singularity 这类 `target_path: .` 且多个模块共享 Git 根目录的仓库，必要时额外设置 `SVN2GIT_MODULE_HINT` 来消除模块反向映射歧义。

直接 `git push` 仍会被客户端 `pre-push` 拒绝。服务端仓库可以参考 `hooks/templates/pre-receive` 和 `hooks/templates/post-receive`，把 strict server-side 模式接到同一个服务 API。服务生成的 Git commit 会通过 `Svn2Git-Origin: svn` 或 `SVN version ...` 标记避免回环。
