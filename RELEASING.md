# 发布指南（Release Guide）

SchedFlow 通过 GitHub Actions 发布到 PyPI，采用 **Trusted Publishing（OIDC 受信发布）**，
CI 中无需保存任何 API Token。

## 首次配置（一次性）

1. 在 PyPI（以及 TestPyPI，如需试发布）的 Account settings → Publishing 中添加 Trusted Publisher：

   - Project：`schedflow`
   - Provider：GitHub
   - Repository：`freedomgod/schedflow`
   - Workflow name：`Publish to PyPI`（必须与 `.github/workflows/publish.yml` 的 `name` 一致）
   - Environment：`release`（可选，与工作流中的 environment 对应）

2. 在 GitHub 仓库 Settings → Environments 中创建 `release` 环境（可选：添加审批人/保护规则）。

## 发布新版本

1. 更新 `CHANGELOG.md`，合并到 `main`；
2. 在 main 分支上打标签并推送（工作流会校验标签必须指向 main 的提交，dev 上的标签不会发布）：

```bash
git tag v0.1.0
git push origin v0.1.0
```

3. 工作流自动完成：构建 sdist + wheel → `twine check` → 冒烟测试 → 发布 PyPI → 创建 GitHub Release。

## 试发布（TestPyPI）

GitHub Actions 页面 → `Publish to PyPI` → Run workflow → 勾选 `test_pypi` 后运行，
产物会发布到 TestPyPI 而不是 PyPI（需要先在 TestPyPI 配置同名 Trusted Publisher）。

## 说明

- 版本号由 `setuptools_scm` 从 git 标签推导（`v0.1.0` → `0.1.0`）；
- 本项目为纯 Python 包，使用 `python -m build` 构建通用 wheel（`py3-none-any`），
  无需 cibuildwheel 的多平台编译轮子；若未来加入 C/Rust 扩展，
  可参照 <https://github.com/pypa/cibuildwheel> 增加平台矩阵构建。