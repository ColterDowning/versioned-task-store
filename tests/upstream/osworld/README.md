# Pinned OSWorld test fixtures

`task_loader.py`, `desktop_env/task_base.py`, and `LICENSE` are unchanged copies
from https://github.com/xlang-ai/OSWorld-V2 at commit
`12083cf1ad95d19875c1eedb77cf59e9408b939e`.

The empty `desktop_env/__init__.py` is local test scaffolding: it allows importing
the real task interface without importing the full desktop environment package.

The compatibility test uses the upstream loader and BaseTask, with test doubles
for setup and desktop interaction. It does not launch an OSWorld VM. Its example
uses paths relative to `__file__`, so no `OSWORLD_FILE_BASE_URL` is needed.

Run from the repository root with `python -m pytest -q tests/test_storer.py`.
