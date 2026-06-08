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
  example:
    svn_url: http://127.0.0.1:8443/repo/example
    svn_project_path: F:\SvnRepo\SMPlatform
    git_project_path: F:\GitRepo\Platform
    dir_regx: .*/branches/([^/]+).*
```

由于项目结构复杂，不同的项目通过 `dir_regx` 正则表达式匹配分支...我太难了...

#### Git 子模块映射

如果多个 SVN 项目来自同一个 SVN 地址、只是工作副本路径不同，可以在同一个 Git 大项目下配置为子模块。子模块默认继承父仓库的 `svn_url`、`dir_regx` 和 `dir_suffix`，也可以单独覆盖。

```yaml
svn_git_mapping:
  suite:
    svn_url: https://svn.example.com/repos/main
    svn_project_path: F:\SvnRepo\Suite
    git_project_path: F:\GitRepo\Suite
    dir_regx: .*/branches/([^/]+).*
    submodules:
      billing:
        svn_project_path: F:\SvnRepo\Billing
        git_submodule_path: modules/billing
        git_remote_url: ssh://git.example.com/suite/billing.git
        branch_overrides:
          dev:
            svn_url: https://svn.example.com/repos/billing-dev
            svn_project_path: F:\SvnRepo\BillingDev
          "2.13":
            svn_url: https://192.168.0.182:8443/repo/codes/SafeMg/Singularity/Common/2.13/common
            svn_project_path: F:\SvnTest\SingularityCommon-2.13
            dir_suffix: common
          platform_2.13:
            svn_url: https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches/platform_2.13
            svn_project_path: F:\SvnTest\SingularityFramework-2.13
            dir_regx: .*/branches/([^/]+)/.*
            branch_name: "2.13"
      reporting:
        svn_project_path: F:\SvnRepo\Reporting
        git_submodule_path: modules/reporting
        git_remote_url: ssh://git.example.com/suite/reporting.git
        dir_regx: .*/release/([^/]+).*
```

同步时会先确保父 Git 仓库中存在对应子模块，再分别同步每个子模块工作区，最后在父仓库提交 `.gitmodules` 和子模块指针变更。

如果同一个模块的不同分支来自不同 SVN 仓库或不同工作副本路径，可以使用 `branch_overrides` 指定分支级来源。上例中 `billing` 模块的 `dev` 分支会使用 `https://svn.example.com/repos/billing-dev` 和 `F:\SvnRepo\BillingDev`。Common 的 `2.13` 分支会使用 `.../Singularity/Common/2.13/common`，分支名仍是 `2.13`，并通过 `dir_suffix: common` 去掉工作副本根目录前的 `common` 路径段；framework 的来源路径分支是 `platform_2.13`，会使用 `.../SMPlatform/branches/platform_2.13`，通过自己的 `dir_regx` 识别该分支下的任意模块路径，并通过 `branch_name: "2.13"` 同步到 Git 的 `2.13` 分支。其他分支仍使用 `billing` 模块自己的 `svn_project_path` 和 `dir_regx`，没有单独配置 `svn_url` 时继续继承父仓库的 `svn_url`。

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

此部分需要在客户端配置 Git Hook，以便在提交到 Git 仓库时拦截并将变更转提交到 SVN 仓库

逻辑如下:

- [x] 提交白名单: 在 Git 项目中提交白名单内的文件时不会转提到 SVN 项目中
- [x] 获取本次的 commit message, 仅在 IDEA 上测试过, 命令行等其他提交方式未测试
- [x] 获取 SVN 仓库信息
- [x] 检查 Git 代码是否最新
- [x] 检查 SVN Git 同步状态
- [x] 获取并添加从 Git 项目中新增或修改的文件到 SVN 项目中
- [x] 获取并删除从 Git 项目中删除的文件到 SVN 项目中
- [x] 提交 SVN 代码
- [x] 调用代码同步接口立刻触发项目同步
- [x] 拒绝 Git 提交

由于 SVN 项目结构复杂混乱，不同项目的结构也不相同, 详见 [Singularity](hooks%2FSingularity) 钩子脚本
