"""pytest configuration for async tests"""
import pytest

pytest_plugins = ('pytest_asyncio',)

# These test files reference modules that have been renamed/removed
collect_ignore = [
    "test_generic_usp_binding.py",
    "test_uds_usp_binding.py",
]
