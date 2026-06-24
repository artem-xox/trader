"""Tests for the calculator's safe arithmetic evaluator.

`safe_eval` is the security-sensitive core of the `calculator` tool: it must compute real
arithmetic and reject anything that is not arithmetic (no attribute access, no arbitrary
calls), so it is tested offline.
"""

from __future__ import annotations

import math

import pytest

from trader.core.tools.calc import safe_eval


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("2 ** 10", 1024),
        ("-5 + 3", -2),
        ("7 // 2", 3),
        ("7 % 3", 1),
        ("0.62 * (1 / 0.55 - 1) - 0.38", 0.62 * (1 / 0.55 - 1) - 0.38),
        ("sqrt(16)", 4),
        ("max(1, 2, 3)", 3),
        ("round(3.14159, 2)", 3.14),
    ],
)
def test_evaluates_arithmetic(expression, expected):
    assert safe_eval(expression) == pytest.approx(expected)


def test_uses_constants():
    assert safe_eval("pi") == pytest.approx(math.pi)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",  # no calls outside the whitelist
        "open('/etc/passwd')",
        "x + 1",  # unknown name
        "[1, 2, 3]",  # no containers
        "1 if True else 2",  # no conditionals
        "9 ** 9 ** 9",  # exponent guard
        "1 +",  # syntax error
    ],
)
def test_rejects_non_arithmetic(expression):
    with pytest.raises(ValueError):
        safe_eval(expression)
