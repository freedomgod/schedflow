# Contributing

Contributions are welcome! Here is how to get involved.

## Setting up the development environment

```bash
# Clone the repository
git clone https://github.com/freedomgod/schedflow.git
cd schedflow

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Editable install with test and doc dependencies
pip install -e .[test,web,sqlalchemy,doc]
```

## Running tests

```bash
# Run the full suite
pytest

# Run a specific test file
pytest tests/core/test_workflow.py

# Coverage report
pytest --cov=schedflow --cov-report=html
```

Some tests require external services (MongoDB, Redis). Start them with Docker Compose:

```bash
docker compose up -d
pytest
docker compose down
```

## Code style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
ruff check .
ruff format .
```

## Building the docs

```bash
pip install -e .[doc]
mkdocs serve     # live preview at http://localhost:8000
mkdocs build     # build the static site into site/
```

### Documentation conventions

- Docs use **mkdocs-static-i18n** with the `suffix` layout: every page exists as both `*.zh.md` (Chinese, the default language) and `*.en.md` (English). Keep both in sync;
- Chinese is the primary version at the site root; English lives under `/en/`;
- New pages must be added to the `nav` in `mkdocs.yml` (plus `nav_translations` entries when needed), otherwise the build warns about pages not in the nav;
- Code examples in the docs must be runnable; re-run them after API changes;
- The homepage language-switcher links are rewritten to relative paths by `hooks.py` at the repository root, so they work under both `mkdocs serve` and the Read the Docs deployment; keep it in sync when touching language-related logic;
- On Read the Docs, `site_url` must match the RTD language prefix (currently `https://schedflow.readthedocs.io/zh-cn/latest/`), or language-switcher links will 404.

## Pull request workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests and linters
5. Commit with a clear message
6. Push and open a Pull Request

## Commit message conventions

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation changes
- `chore:` — maintenance
- `test:` — test changes
- `refactor:` — code refactoring
