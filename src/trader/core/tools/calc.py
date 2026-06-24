"""Safe arithmetic evaluator for the `calculator` tool.

LLMs are unreliable at exact arithmetic, but evaluating model-supplied text with `eval`
is a code-execution hole. This walks a parsed AST and allows only numeric literals,
arithmetic operators, and a small whitelist of math functions/constants — nothing else
(no names, attributes, comprehensions, or calls outside the whitelist).
"""

from __future__ import annotations

import ast
import math
import operator

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt,
    "log": math.log,  # log(x) natural, or log(x, base)
    "ln": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e}

# Guard against pathological inputs like 9**9**9 that would hang the process.
_MAX_EXPONENT = 1000


def safe_eval(expression: str) -> float:
    """Evaluate an arithmetic expression, raising ValueError on anything unsupported."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid expression: {exc.msg}") from exc
    return _eval(tree.body)


def _eval(node: ast.expr) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"unsupported literal: {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        left, right = _eval(node.left), _eval(node.right)
        if op is operator.pow and abs(right) > _MAX_EXPONENT:
            raise ValueError("exponent too large")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")
        return op(_eval(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ValueError("unsupported function call")
        if node.keywords:
            raise ValueError("keyword arguments are not supported")
        return _FUNCS[node.func.id](*(_eval(arg) for arg in node.args))
    if isinstance(node, ast.Name):
        if node.id not in _CONSTS:
            raise ValueError(f"unknown name: {node.id!r}")
        return _CONSTS[node.id]
    raise ValueError(f"unsupported expression: {type(node).__name__}")
