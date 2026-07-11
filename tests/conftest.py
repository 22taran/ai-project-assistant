"""
Shared pytest configuration for the whole-suite run.

Both tests/ack/test_handler.py and tests/worker/test_handler.py insert their
respective lambda/<component> directory onto sys.path and then do
`importlib.import_module("handler")` to load the module under test (both
files under test happen to be named `handler.py`, one per lambda).

That per-file `sys.path.insert(0, ...)` runs at *collection* time (it's
module-level code), so by the time pytest starts *running* tests, every test
file in the suite has already inserted its directory. Whichever directory
was inserted last ends up first on sys.path for the rest of the run,
regardless of which test is actually executing next. That silently makes an
ack test resolve `import_module("handler")` to lambda/worker/handler.py (or
vice versa) when the whole suite runs together, even though each test file
passes fine in isolation.

This autouse fixture repairs sys.path immediately before each test item
runs: it promotes the lambda directory matching the *currently executing*
test file's own subpackage (tests/ack -> lambda/ack, tests/worker ->
lambda/worker) to the front of sys.path, and evicts any same-named module
already cached in sys.modules from the wrong directory. This does not touch
any existing test file or lambda source file.
"""
import pathlib
import sys

import pytest

_TESTS_ROOT = pathlib.Path(__file__).resolve().parent
_LAMBDA_ROOT = _TESTS_ROOT.parent / "lambda"


@pytest.fixture(autouse=True)
def _prioritize_matching_lambda_dir(request):
    test_file = pathlib.Path(str(request.node.fspath)).resolve()
    try:
        rel = test_file.relative_to(_TESTS_ROOT)
    except ValueError:
        yield
        return

    subdir = rel.parts[0] if rel.parts else None
    target_dir = _LAMBDA_ROOT / subdir if subdir else None

    if target_dir and target_dir.is_dir():
        target = str(target_dir)
        while target in sys.path:
            sys.path.remove(target)
        sys.path.insert(0, target)

        # Evict any module cached from a sibling lambda directory so a
        # stale import doesn't shadow the one this test actually wants.
        for modname, mod in list(sys.modules.items()):
            mod_file = getattr(mod, "__file__", None)
            if not mod_file:
                continue
            if mod_file.startswith(str(_LAMBDA_ROOT)) and not mod_file.startswith(target):
                del sys.modules[modname]

    yield
