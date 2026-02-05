# Contributing to AI Secretary System

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (for containerized development)
- NVIDIA GPU with 12GB+ VRAM (for GPU features, optional)

### Local Setup

```bash
# Clone repository
git clone https://github.com/ShaerWare/AI_Secretary_System
cd AI_Secretary_System

# Create Python virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -r requirements.txt
pip install ruff mypy pre-commit pytest pytest-asyncio pytest-cov

# Install pre-commit hooks
pre-commit install

# Setup admin panel
cd admin && npm install && cd ..

# Copy environment file
cp .env.docker.example .env
```

## Code Style

### Python
- We use **ruff** for linting and formatting
- Line length: 100 characters
- Cyrillic characters allowed in strings (Russian language support)

```bash
# Check code
ruff check .

# Auto-fix issues
ruff check . --fix

# Format code
ruff format .
```

### TypeScript/Vue
- We use **ESLint** and **Prettier**

```bash
cd admin
npm run lint
```

### Pre-commit
All checks run automatically on commit:

```bash
# Run all checks manually
pre-commit run --all-files
```

## Pull Request Process

### 1. Create a Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 2. Make Changes
- Follow existing code patterns
- Add tests for new functionality
- Update documentation if needed

### 3. Test Your Changes
```bash
# Python tests
pytest tests/ -v

# Linting
ruff check .
ruff format --check .

# Frontend
cd admin && npm run lint && npm run build
```

### 4. Commit
Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new TTS voice preset
fix: resolve chat session memory leak
docs: update API documentation
refactor: simplify LLM provider factory
test: add unit tests for FAQ service
chore: update dependencies
```

### 5. Push and Create PR
```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub with:
- Clear description of changes
- Link to related issue (if any)
- Screenshots for UI changes

## Project Structure

```
AI_Secretary_System/
├── orchestrator.py          # FastAPI entry point
├── app/
│   ├── routers/             # API endpoints (15 routers)
│   ├── dependencies.py      # Dependency injection
│   ├── rate_limiter.py      # Rate limiting
│   └── security_headers.py  # Security middleware
├── db/
│   ├── models.py            # SQLAlchemy models
│   └── repositories/        # Data access layer
├── admin/                   # Vue 3 admin panel
│   ├── src/views/           # Page components
│   ├── src/api/             # API clients
│   └── src/stores/          # Pinia stores
├── tests/                   # Test suite
└── docs/                    # Documentation
```

## Adding New Features

### New API Endpoint
1. Create or edit router in `app/routers/`
2. Use `ServiceContainer` from `app/dependencies.py`
3. Router auto-registers via `app/routers/__init__.py`

### New Cloud LLM Provider
1. Add entry to `PROVIDER_TYPES` in `db/models.py`
2. If OpenAI-compatible, it works automatically
3. For custom SDK, create provider class in `cloud_llm_service.py`

### New Admin Panel Tab
1. Create view in `admin/src/views/`
2. Add route in `admin/src/router/index.ts`
3. Add translations in `admin/src/plugins/i18n.ts`

## Testing

### Running Tests
```bash
# All tests
pytest tests/ -v

# Specific file
pytest tests/unit/test_db.py -v

# By pattern
pytest -k "test_chat" -v

# Exclude slow/integration tests
pytest -m "not slow and not integration" -v

# With coverage
pytest --cov --cov-report=html
```

### Test Markers
- `@pytest.mark.slow` - Long-running tests
- `@pytest.mark.integration` - Requires external services
- `@pytest.mark.gpu` - Requires CUDA GPU

## Reporting Issues

When reporting bugs, please include:
- Python version (`python --version`)
- OS and version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs from `logs/orchestrator.log`

## Security

If you discover a security vulnerability, please email directly instead of creating a public issue.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Questions? Open an issue or check [CLAUDE.md](./CLAUDE.md) for detailed documentation.
