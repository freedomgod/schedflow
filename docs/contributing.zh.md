# 贡献指南

欢迎贡献！以下是参与方式。

## 开发环境搭建

```bash
# 克隆仓库
git clone https://github.com/freedomgod/schedflow.git
cd schedflow

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 以可编辑模式安装，包含测试与文档依赖
pip install -e .[test,web,sqlalchemy,doc]
```

## 运行测试

```bash
# 运行全部测试
pytest

# 运行特定测试文件
pytest tests/core/test_workflow.py

# 运行覆盖率测试
pytest --cov=schedflow --cov-report=html
```

部分测试需要外部服务（MongoDB、Redis）。使用 Docker Compose 启动它们：

```bash
docker compose up -d
pytest
docker compose down
```

## 代码风格

我们使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查和格式化：

```bash
# 安装 pre-commit 钩子
pre-commit install

# 手动运行
ruff check .
ruff format .
```

## 构建文档

```bash
pip install -e .[doc]
mkdocs serve     # 实时预览 http://localhost:8000
mkdocs build     # 构建静态网站到 site/
```

### 文档组织约定

- 文档采用 **mkdocs-static-i18n** 的 `suffix` 结构，每个页面同时存在 `*.zh.md`（中文，默认语言）与 `*.en.md`（英文）两个版本，改文档时两个版本必须同步更新；
- 中文文档是主版本，位于站点根路径；英文版位于 `/en/`；
- 新增页面必须同时加入 `mkdocs.yml` 的 `nav`（以及必要的 `nav_translations`），否则会出现 “pages exist ... not included in the nav” 警告；
- 文档中的代码示例必须可运行，改动 API 相关文档后请在本地跑一遍示例；
- 语言切换下拉框在首页的链接由仓库根目录 `hooks.py` 修正为相对路径，`mkdocs serve` 与 Read the Docs 部署下均可用，改动语言相关逻辑时需同步更新；
- 部署到 Read the Docs 时，站点的 `site_url` 必须与 RTD 语言前缀一致（当前为 `https://schedflow.readthedocs.io/zh-cn/latest/`），否则语言切换链接会 404。

## Pull Request 流程

1. Fork 仓库
2. 创建功能分支（`git checkout -b feature/my-feature`）
3. 进行修改
4. 运行测试和代码检查
5. 使用清晰的提交信息提交
6. 推送并创建 Pull Request

## 提交规范

- `feat:`——新功能
- `fix:`——Bug 修复
- `docs:`——文档变更
- `chore:`——维护任务
- `test:`——测试变更
- `refactor:`——代码重构
