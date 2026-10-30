import doctest
import importlib
import pkgutil

import pytest

import guildkit

MODULES = sorted(m.name for m in pkgutil.iter_modules(guildkit.__path__, "guildkit."))


@pytest.mark.parametrize("name", MODULES)
def test_doctests(name: str) -> None:
    module = importlib.import_module(name)
    result = doctest.testmod(module, optionflags=doctest.NORMALIZE_WHITESPACE)
    assert result.failed == 0
