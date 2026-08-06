# 协作指南

## 首次准备

1. 接受仓库协作者邀请。
2. 克隆仓库，不要下载 ZIP 后直接改代码。
3. 配置自己的 Git 用户名和邮箱。
4. 切换到分配给自己的功能分支，再开始编辑。

## 分支职责

- A：`feature/firmware-node`，只改 `firmware_esp32s3/`。
- B：`feature/pc-receiver`，只改 `pc_receiver/`。
- C：`feature/fusion-3d`，只改 `analysis/` 和 `desktop_app/`。
- `main` 始终保持可联调；任何人都不要直接向 `main` 推送日常开发提交。

如果必须修改 `docs/`、`samples/`、`.gitignore` 或根目录依赖文件，先创建独立的小 Pull Request，说明对另外两人的影响。

## 每天的基本流程

```bash
git switch <你的分支>
git pull --ff-only
git status
git add <本次修改的明确文件>
git commit -m "简短说明本次完成的内容"
git push
```

提交前确认没有密钥、构建产物、录制数据或无关文件。不要使用 `git add .` 来掩盖自己不理解的改动。

## 合并流程

1. 在 GitHub 上从个人负责分支向 `main` 创建 Pull Request。
2. 至少由另一位成员检查代码和接口兼容性。
3. 确认能构建或运行相应测试。
4. 合入后，其他成员把最新 `main` 合并到自己的分支并解决冲突。

公共协议改动必须同时更新 `docs/data-protocol.md` 和 `samples/` 中的测试数据。
