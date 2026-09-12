# 分发仓库开发入口

本仓库维护公开 Issue、安装器、渠道元数据与发布编排。Runtime 和 UI 分别在独立仓库实现；只修改本次受影响的仓库。

## 工作约定

- 改动前 `git fetch --prune origin`，确认 `git merge-base --is-ancestor origin/main HEAD` 成功；保留已有未提交改动。
- 以最小完整改动解决当前需求，不增加假设性扩展或重复的流程文档。
- 讨论、计划和审查交付相应产物。用户可见功能的实现使用 [.agents/skills/aeloon-issue-flow/SKILL.md](.agents/skills/aeloon-issue-flow/SKILL.md)；内部维护不套用公开产品 Issue 流程。
- 实现完成相关验证并修复本次引入的问题；报告实际结果和具体阻碍，不在常规可继续步骤重复索取确认。
- 用户要求提交 PR 时，交付可审查的 PR 和实际 CI 状态；合并与发布遵循请求及已有授权确定的终点。
- 技能按实际产物选择，先读入口，再按当前阶段查参考章节；不要因关键词重叠加载整套技能。

## 按任务定位

| 任务 | 代码或文档 |
| --- | --- |
| 桌面安装、卸载 | `install.sh`、`install.ps1`、`uninstall.sh`、`uninstall.ps1` |
| 服务器安装、卸载 | `install-server.sh`、`uninstall-server.sh`；部署行为见 [docs/remote-deployment.md](docs/remote-deployment.md) |
| 版本选择与回滚 | `channels/desktop/stable`、`channels/runtime/stable` |
| 候选包或发布 | [docs/releasing.md](docs/releasing.md)、`.github/workflows/candidate.yml`、`.github/workflows/publish.yml`、`tools/publish_release.sh` |
| Issue、PR 关联与状态同步 | [docs/issue-workflow.md](docs/issue-workflow.md)、`tools/issue_flow.py`、`.github/actions/public-issue-policy/` |

公开 Issue 和 Release 只包含用户可见的结果；私有仓库的实现细节、日志和凭证不进入公开产物。

## 验证与交付

- 文档或技能改动检查引用、前置条件、任务边界和格式；不因此执行安装或发布。
- 修改安装或编排逻辑时，先运行 `tests/` 中受影响的 unittest；分发 CI 的本地入口是 `python3 -m unittest discover -s tests -v` 与 `bash -n tools/publish_release.sh`。
- 修改其他 Shell 脚本时，对相应文件执行 `bash -n`；PowerShell 和各平台安装验收依照已有 CI。
- 通过后没有新改动或失败，不重复全套检查。提交仍满足所需 CI。
- Runtime、UI 依赖顺序和候选包提升规则以发布文档为准。稳定版 Desktop 发布是单独的明确请求。
