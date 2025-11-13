# Contributing to WaybackPress

Thank you for your interest in contributing to WaybackPress. This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful and constructive in all interactions. We are building this tool to help the WordPress community recover lost content.

## How to Contribute

### Reporting Bugs

When reporting bugs, please include:

- Your Python version (`python --version`)
- WaybackPress version (`waybackpress --version`)
- Complete command you ran
- Expected behavior vs. actual behavior
- Relevant log output or error messages
- Domain being recovered (if not sensitive)

### Suggesting Features

Feature requests are welcome. Please:

- Check if the feature already exists
- Explain the use case clearly
- Describe expected behavior
- Consider implementation complexity

### Code Contributions

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Add tests for new functionality
5. Run tests and linting
6. Submit a pull request

## Development Setup

```bash
git clone https://github.com/stardothosting/shift8-waybackpress.git
cd shift8-waybackpress
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
pip install -e .
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints for function parameters and returns
- Write docstrings for public functions and classes
- Keep functions focused and under 50 lines when possible
- Use meaningful variable names

Format code with Black:

```bash
black waybackpress/
```

## Testing

Run the test suite:

```bash
python -m pytest tests/
```

Add tests for new features in the `tests/` directory.

## Documentation

- Update README.md for user-facing changes
- Add docstrings for new functions
- Update examples/ for new features
- Keep documentation clear and concise

## Commit Messages

Use clear, descriptive commit messages:

```
Add multi-snapshot retry for media fetching

- Query CDX API for alternative snapshots
- Attempt up to 5 snapshots per file
- Track attempted timestamps in report
```

## Pull Request Process

1. Ensure all tests pass
2. Update documentation as needed
3. Add a clear description of changes
4. Reference any related issues
5. Wait for review and address feedback

## Areas for Contribution

### High Priority

- Additional CMS support (Drupal, Joomla)
- Improved content heuristics
- Better duplicate detection
- Performance optimizations

### Medium Priority

- GUI interface
- Docker container
- Cloud deployment options
- Integration tests

### Low Priority

- Additional export formats
- Theme/plugin recovery
- Comment thread reconstruction

## Questions?

Open a discussion on GitHub or email info@shift8web.ca

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

