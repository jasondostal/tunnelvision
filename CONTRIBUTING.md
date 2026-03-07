# Contributing to TunnelVision

Thanks for your interest in contributing!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/jasondostal/tunnelvision.git
cd tunnelvision

# Backend (Python 3.12+)
python -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

# Frontend (Node 20+)
cd ui && npm install && cd ..

# Run tests
pytest tests/

# Run linters
ruff check api/ tests/
mypy api/
```

## Code Style

- **Python**: Ruff for linting, mypy for type checking
- **TypeScript**: ESLint
- **Shell**: ShellCheck
- All CI checks must pass before merge

## Pull Request Process

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with tests
4. Ensure all CI checks pass (`pytest`, `ruff`, `mypy`, `shellcheck`)
5. Submit a PR with a clear description

## Architecture

- `api/` — FastAPI backend (Python 3.12)
- `ui/` — React 19 + Vite + Tailwind v4 frontend
- `rootfs/` — s6-overlay service definitions and init scripts
- `tests/` — pytest test suite

## Adding a VPN Provider

Providers are auto-discovered via `pkgutil`. To add a new provider:

1. Create `api/services/providers/yourprovider.py`
2. Implement the `VPNProvider` interface (see existing providers for examples)
3. Add tests in `tests/test_yourprovider.py`
4. The provider will be automatically available — no registry edits needed
