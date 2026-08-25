import pytest

from jottermem import Memory


@pytest.fixture
def memory():
    with Memory(path=":memory:") as m:
        yield m
