# Contributing to Mail-Rulez

We welcome contributions to Mail-Rulez! This document provides guidelines for contributing to the project.

## Code of Conduct

Please be respectful and professional in all interactions with the project.

## How to Contribute

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes**
4. **Add tests** for new functionality
5. **Ensure all tests pass** (`pytest`)
6. **Commit your changes** (`git commit -m 'Add amazing feature'`)
7. **Push to your fork** (`git push origin feature/amazing-feature`)
8. **Open a Pull Request**

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/mail-rulez.git
cd mail-rulez

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest
```

## Pull Request Guidelines

- Include tests for new functionality
- Update documentation as needed
- Follow existing code style
- Keep commits focused and atomic
- Write clear commit messages

## Licensing

By contributing to Mail-Rulez, you agree that your contributions will be licensed under the same dual license as the project (AGPL v3 for open source use, commercial license for hosted services).

## Questions?

Feel free to open an issue for any questions about contributing.
