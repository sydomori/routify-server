import pytest

@pytest.fixture(autouse=True)
def _app_context(app):
    """Make sure the app context is pushed for every test, so that code that uses
    current_app or current_user works without having to push it manually in each test."""
    yield