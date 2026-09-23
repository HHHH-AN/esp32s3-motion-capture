# 协作说明

## 目录责任

- ZBC：`旧版/IMU-tracker/**`
- HAN：`旧版/pose/backend/**`
- 项目负责人：`旧版/contracts/**`、`.github/**`、`旧版/pose/frontend/**`

跨目录修改必须提前在 PR 中说明原因。

## 合并顺序

1. 公共接口先通过独立 Contract PR 合入 `main`。
2. HAN 先实现接收端兼容。
3. ZBC 再切换发送端。
4. 项目负责人完成端到端验收。
5. PR 合并后，ZBC 和 HAN 将最新 `main` merge 回长期个人分支。

已推送的 `ZBC`、`HAN` 分支禁止 rebase 和 force push。仓库使用 merge commit 保留里程碑历史。

## PR 要求

- 一个 PR 只完成一个可验收目标。
- 普通 PR 至少一名非作者批准。
- `旧版/contracts/**` 变更需要 ZBC、HAN 两人审核。
- CI 必须通过，评论必须解决。
- 不提交构建产物、依赖目录、个人录制、个人标定、日志、密钥或 `.env`。
- Golden Vectors 只能在 Contract PR 中修改。

## 提交信息

使用简洁的 Conventional Commits 风格，例如：

```text
feat(firmware): add ICM FIFO acquisition
feat(backend): decode wire protocol v1
test(contracts): add truncated frame vector
docs(hardware): record PCB revision B
```
