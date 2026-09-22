import os
from pathlib import Path

import pytest

from storer import VersionedTaskStore


@pytest.mark.skipif(
    os.environ.get("RUN_OSWORLD_INTEGRATION") != "1",
    reason="Requires a configured OSWorld desktop; set RUN_OSWORLD_INTEGRATION=1",
)
def test_export_in_real_osworld(tmp_path, monkeypatch):
    vm_path = os.environ.get("OSWORLD_TEST_VM_PATH")
    if not vm_path or not Path(vm_path).is_file():
        pytest.fail("Set OSWORLD_TEST_VM_PATH to an existing OSWorld VM image")
    vm_path = str(Path(vm_path).resolve())

    from desktop_env.desktop_env import DesktopEnv
    from task_loader import load_task_from_file

    fixture = (
        Path(__file__).resolve().parent / "fixtures" / "uppercase"
    )
    store = VersionedTaskStore(str(tmp_path / "store"))
    task_name = store.create(fixture)
    exported = tmp_path / "export"
    store.export(task_name, 1, exported)

    moved = tmp_path / "moved-export"
    exported.rename(moved)
    unrelated = tmp_path / "elsewhere"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    task = load_task_from_file(str(moved / "task_001.py"))
    env = DesktopEnv(
        provider_name=os.environ.get("OSWORLD_TEST_PROVIDER", "docker"),
        path_to_vm=vm_path,
        snapshot_name="init_state",
        action_space="pyautogui",
        headless=True,
        require_a11y_tree=False,
        cache_dir=str(tmp_path / "cache"),
    )

    try:
        env.reset(task_config=task)
        assert env.controller.get_file("/home/user/input.txt") == b"hello\n"

        env.controller.execute_python_command(
            "from pathlib import Path; "
            "Path('/home/user/result.txt').write_bytes(b'hello\\n')"
        )
        assert env.controller.get_file("/home/user/result.txt") == b"hello\n"
        assert env.evaluate() == 0.0

        env.controller.execute_python_command(
            "from pathlib import Path; "
            "Path('/home/user/result.txt').write_bytes(b'HELLO\\n')"
        )
        assert env.controller.get_file("/home/user/result.txt") == b"HELLO\n"
        assert env.evaluate() == 1.0
    finally:
        env.close()
