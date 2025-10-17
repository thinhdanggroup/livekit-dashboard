# Contributing to LiveKit Dashboard

Thank you for your interest in contributing to LiveKit Dashboard! This document provides guidelines and instructions for contributing.

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- Poetry (for dependency management)
- Git
- A LiveKit server instance for testing (optional)

### Setup Development Environment

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/your-username/livekit-dashboard.git
   cd livekit-dashboard
   ```

2. **Install dependencies**
   ```bash
   make install
   # or
   poetry install
   ```

3. **Create environment file**
   ```bash
   make env-example
   # Edit .env with your configuration
   ```

4. **Run the development server**
   ```bash
   make dev
   ```

## 📝 Development Guidelines

### Code Style

We use the following tools to maintain code quality:

- **Black**: Code formatting (line length: 100)
- **Ruff**: Linting
- **mypy**: Type checking

Run all formatters and linters:
```bash
make fmt    # Format code
make lint   # Run linters
```

### Commit Messages

Follow conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Example:
```
feat: add participant search functionality
fix: resolve token generation error
docs: update README with deployment instructions
```

### Branch Naming

- `feature/description` - New features
- `bugfix/description` - Bug fixes
- `hotfix/description` - Critical fixes
- `docs/description` - Documentation updates

## 🧪 Testing

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
poetry run pytest tests/test_main.py -v
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files as `test_*.py`
- Name test functions as `test_*`
- Use fixtures from `tests/conftest.py`
- Follow the existing test structure

Example:
```python
def test_new_feature(client, auth_headers):
    """Test description"""
    response = client.get("/endpoint", headers=auth_headers)
    assert response.status_code == 200
```

### Test Guidelines

- Write tests for new features
- Update tests when modifying existing features
- Ensure all tests pass before submitting PR
- Aim for meaningful test coverage
- Mock external dependencies (LiveKit SDK calls)

## 📦 Adding Dependencies

If you need to add a new dependency:

1. Add it using Poetry:
   ```bash
   poetry add package-name
   # or for dev dependencies
   poetry add --group dev package-name
   ```

2. Update `pyproject.toml` with version constraints
3. Run `poetry lock` to update the lock file
4. Document why the dependency is needed in your PR

## 🔧 Project Structure

```
livekit-dashboard/
├── app/
│   ├── main.py              # Application entry point
│   ├── routes/              # Route handlers
│   ├── services/            # Business logic
│   ├── security/            # Security modules
│   ├── templates/           # Jinja2 templates
│   └── static/              # Static assets
├── tests/                   # Test files
├── docs/                    # Documentation
└── ...
```

## 🐛 Reporting Bugs

When reporting bugs, please include:

1. **Description**: Clear description of the bug
2. **Steps to reproduce**: Detailed steps to reproduce the issue
3. **Expected behavior**: What you expected to happen
4. **Actual behavior**: What actually happened
5. **Environment**:
   - OS and version
   - Python version
   - LiveKit server version
   - Dashboard version
6. **Logs**: Relevant error messages or logs
7. **Screenshots**: If applicable

Use the bug report template when creating an issue.

## 💡 Suggesting Features

When suggesting features:

1. **Use case**: Describe the problem you're trying to solve
2. **Proposed solution**: How you envision the feature working
3. **Alternatives**: Other solutions you've considered
4. **Additional context**: Any other relevant information

## 🔄 Pull Request Process

1. **Create a branch** from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, documented code
   - Follow the code style guidelines
   - Add tests for new functionality
   - Update documentation if needed

3. **Test your changes**
   ```bash
   make test
   make lint
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add your feature"
   ```

5. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a Pull Request**
   - Use a clear, descriptive title
   - Reference any related issues
   - Describe your changes in detail
   - Include screenshots if applicable
   - List any breaking changes

### PR Checklist

- [ ] Code follows the project style guidelines
- [ ] Tests pass locally (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] New tests added for new functionality
- [ ] Documentation updated (if needed)
- [ ] Commits follow conventional commit format
- [ ] PR description is clear and complete
- [ ] No unrelated changes included

## 📚 Documentation

When adding or updating features:

- Update relevant docstrings
- Update README.md if needed
- Add comments for complex logic
- Update API documentation
- Include examples where helpful

## 🎯 Areas for Contribution

Here are some areas where contributions are especially welcome:

- **Features**: New functionality (see Issues labeled `enhancement`)
- **Bug Fixes**: Issues labeled `bug`
- **Documentation**: Improvements to README, guides, examples
- **Tests**: Improving test coverage
- **Performance**: Optimization improvements
- **UI/UX**: Template and styling improvements
- **Accessibility**: Making the dashboard more accessible

## 🤝 Code Review Process

All submissions require review:

1. **Automated checks**: CI pipeline must pass
2. **Code review**: At least one maintainer approval
3. **Testing**: Reviewer will test the changes
4. **Feedback**: Address any requested changes
5. **Merge**: Once approved, changes will be merged

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 💬 Getting Help

- **Issues**: GitHub Issues for bug reports and feature requests
- **Discussions**: GitHub Discussions for questions and ideas
- **Discord**: Join the LiveKit Discord community

## 🙏 Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes for significant contributions
- GitHub contributors page

Thank you for contributing to LiveKit Dashboard! 🎉

