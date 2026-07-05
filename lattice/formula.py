"""Safe evaluator for formula-type cells: INPT plus + - * / on integers only.

Not a general calculator on purpose. This parses with ``ast`` instead of
``eval()`` and only allows integer literals, the ``INPT`` placeholder, and the
four basic binary operators — nothing else can ever run here, so a formula
string (which a user can type freely) can never execute arbitrary code.
"""

from __future__ import annotations

import ast
import operator

# ponytail: / is floor division so results stay integers; true division with
# rounding can come later if a formula actually needs a non-whole result.
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.floordiv,
}


def validate(text: str) -> bool:
    """True if `text` only uses INPT, integer literals, and + - * /."""
    try:
        _tree(text)
        return True
    except ValueError:
        return False


def evaluate(text: str, inpt: int) -> int:
    """Run `text`, substituting INPT with the user-supplied integer."""
    return _eval(_tree(text).body, inpt)


def _tree(text: str) -> ast.Expression:
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(str(exc)) from exc
    _check(tree.body)
    return tree


def _check(node: ast.AST) -> None:
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        _check(node.left)
        _check(node.right)
    elif isinstance(node, ast.Name) and node.id == "INPT":
        pass
    elif (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        pass
    else:
        raise ValueError(f"unsupported expression near {ast.dump(node)}")


def _eval(node: ast.AST, inpt: int) -> int:
    if isinstance(node, ast.BinOp):
        return _OPS[type(node.op)](_eval(node.left, inpt), _eval(node.right, inpt))
    if isinstance(node, ast.Name):
        return inpt
    return node.value  # ast.Constant


def parse_simple(text: str) -> dict:
    """Parse "prefix(formula)suffix" into a {prefix, suffix, formula} spec.

    Raises ValueError if there isn't exactly one balanced (...) group, or the
    formula inside it doesn't validate.
    """
    start = text.find("(")
    if start == -1:
        raise ValueError("wrap the formula in parentheses, e.g. asd(INPT * 2)zxc")
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise ValueError("unbalanced parentheses")
    prefix, inner, suffix = text[:start], text[start + 1:end], text[end + 1:]
    if "(" in suffix or ")" in suffix:
        raise ValueError("only one ( ) group is supported")
    if not validate(inner):
        raise ValueError(f"bad formula: {inner!r}")
    return {"prefix": prefix, "suffix": suffix, "formula": inner}


def demo() -> None:
    assert validate("INPT * 2 * 10")
    assert validate("5 * 2")
    assert not validate("abs(INPT)")
    assert not validate("INPT + 'x'")
    assert not validate("INPT * 2.5")
    assert evaluate("INPT * 2 * 10", 5) == 100
    assert evaluate("INPT / 2", 5) == 2
    print("formula: ok")


if __name__ == "__main__":
    demo()
