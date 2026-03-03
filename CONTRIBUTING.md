# Contributing to HelperLearner

Thank you for your interest in contributing! Here's how to get started.

## Development Setup

1. **Fork and clone** the repository
2. **Create a virtual environment**: `python -m venv venv`
3. **Install dependencies**: `pip install -r requirements.txt`
4. **Copy environment config**: `cp .env.example .env` and fill in values
5. **Run migrations**: `python manage.py migrate`
6. **Run tests**: `python manage.py test`

## Code Style

- Follow PEP 8 conventions
- Use type hints where practical
- Keep functions focused — one responsibility per function
- Write docstrings for all public functions and classes

## Testing

- Write tests for all new features
- Run the full test suite before submitting: `python manage.py test`
- Aim for test coverage on happy paths AND edge cases
- Use `TestCase` for database tests, `SimpleTestCase` for pure logic

## Pull Request Process

1. Create a descriptive branch name: `feature/add-xyz` or `fix/broken-abc`
2. Write a clear PR description explaining **what** and **why**
3. Reference any related issues
4. Ensure CI passes (GitHub Actions)
5. Wait for review — we'll respond within 48 hours

## Reporting Bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Screenshots if it's a UI issue
- Browser/OS information

## Feature Requests

Open an issue with the `enhancement` label describing:
- The problem it solves
- Proposed solution
- Any alternatives considered
