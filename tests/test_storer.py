from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import textwrap

from storer import VersionedTaskStore


def test_required_versioning_workflow(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "uppercase"
    working = tmp_path / "working"
    shutil.copytree(fixture, working)
    task_path = working / "task_001.py"
    asset_path = working / "assets" / "input.txt"
    original_source = task_path.read_bytes()
    original_asset = asset_path.read_bytes()
    store = VersionedTaskStore(str(tmp_path / "store"))

    # 1. Create saves version 1; export it to A.
    task_name = store.create(working)
    assert set(store.history(task_name)) == {"1"}
    export_a = tmp_path / "A"
    store.export(task_name, 1, export_a)
    files_a = {
        path.relative_to(export_a).as_posix(): path.read_bytes()
        for path in export_a.rglob("*")
        if path.is_file()
    }
    assert files_a == {
        "task_001.py": original_source,
        "assets/input.txt": original_asset,
    }

    # 2. Change the instruction, evaluator, and asset together in version 2.
    updated_source = original_source.decode("utf-8").replace(
        'instruction = "Convert input.txt to uppercase and save result.txt."',
        'instruction = "Convert input.txt to lowercase and save result.txt."',
    ).replace(
        'expected = (ASSETS / "input.txt").read_bytes().upper()',
        'expected = (ASSETS / "input.txt").read_bytes().lower()',
    )
    task_path.write_text(updated_source, encoding="utf-8")
    updated_asset = b"WORLD\n"
    asset_path.write_bytes(updated_asset)
    assert store.save(task_name, working, "Switch to lowercase and change input") == 2

    # 3. Show history and the diff, including both source changes.
    history = store.history(task_name)
    assert set(history) == {"1", "2"}
    print("History:")
    print(json.dumps(history, indent=2))
    result = store.diff(task_name, 1, 2)
    assert result["added"] == []
    assert result["removed"] == []
    assert result["changed"] == ["assets/input.txt", "task_001.py"]
    source_diff = result["source_diffs"]["task_001.py"]
    assert '-    instruction = "Convert input.txt to uppercase and save result.txt."' in source_diff
    assert '+    instruction = "Convert input.txt to lowercase and save result.txt."' in source_diff
    assert '-        expected = (ASSETS / "input.txt").read_bytes().upper()' in source_diff
    assert '+        expected = (ASSETS / "input.txt").read_bytes().lower()' in source_diff
    print("Changed files:", result["changed"])
    print(source_diff)

    # 4. Restore version 1, identify the working snapshot, and export it to B.
    store.restore(task_name, 1, working)
    current_version = store.save(task_name, working)
    assert current_version == 1
    export_b = tmp_path / "B"
    store.export(task_name, current_version, export_b)

    # 5. Compare every relative file path and every byte, including working files.
    files_b = {
        path.relative_to(export_b).as_posix(): path.read_bytes()
        for path in export_b.rglob("*")
        if path.is_file()
    }
    working_files = {
        path.relative_to(working).as_posix(): path.read_bytes()
        for path in working.rglob("*")
        if path.is_file()
    }
    assert files_a == files_b == working_files
    print("Exports A and B: identical relative paths and bytes")

    # 6. Version 2 remains accessible and neither history entry was changed.
    assert store.history(task_name) == history
    assert store.show(task_name, 2, "task_001.py") == updated_source.encode("utf-8")
    assert store.show(task_name, 2, "assets/input.txt") == updated_asset
    print("Version 2 remains accessible after restoring version 1")


def test_export_loads_in_osworld_after_moving(tmp_path, monkeypatch):
    upstream = (
        Path(__file__).resolve().parent / "upstream" / "osworld"
    )
    monkeypatch.syspath_prepend(str(upstream))

    from desktop_env.task_base import BaseTask
    from task_loader import load_task_from_file

    working = tmp_path / "working"
    assets = working / "assets"
    assets.mkdir(parents=True)
    (assets / "input.txt").write_bytes(b"hello\n")

    task_source = textwrap.dedent('''\
        from pathlib import Path
        from desktop_env.task_base import BaseTask

        ASSETS = Path(__file__).resolve().parent / "assets"

        class UppercaseTask(BaseTask):
            id = "001"
            instruction = "Convert input.txt to uppercase and save result.txt."
            related_apps = ["gedit"]

            config = [{
                "type": "upload_file",
                "parameters": {
                    "files": [{
                        "local_path": str(ASSETS / "input.txt"),
                        "path": "/home/user/input.txt",
                    }]
                },
            }]

            def evaluate(self, env):
                expected = (ASSETS / "input.txt").read_bytes().upper()
                actual = env.controller.get_file("/home/user/result.txt")
                return float(actual == expected)

        TASK_CLASS = UppercaseTask
    ''')
    (working / "task_001.py").write_text(task_source, encoding="utf-8")

    store = VersionedTaskStore(str(tmp_path / "store"))
    task_name = store.create(working)

    exported = tmp_path / "export"
    store.export(task_name, 1, exported)

    moved = tmp_path / "moved-export"
    exported.rename(moved)
    unrelated = tmp_path / "elsewhere"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    task = load_task_from_file(str(moved / "task_001.py"))

    assert isinstance(task, BaseTask)
    assert type(task).__name__ == "UppercaseTask"
    assert task["id"] == "001"
    assert task["instruction"] == (
        "Convert input.txt to uppercase and save result.txt."
    )
    assert (moved / "task_001.py").read_bytes() == task_source.encode("utf-8")

    class RecordingSetupController:
        def setup(self, config, use_proxy):
            self.config = config
            self.use_proxy = use_proxy

    setup_controller = RecordingSetupController()
    task.setup(setup_controller)

    upload = setup_controller.config[0]["parameters"]["files"][0]
    assert Path(upload["local_path"]) == moved / "assets" / "input.txt"
    assert Path(upload["local_path"]).read_bytes() == b"hello\n"
    assert upload["path"] == "/home/user/input.txt"
    assert setup_controller.use_proxy is False

    class FakeController:
        def __init__(self, result):
            self.result = result

        def get_file(self, path):
            assert path == "/home/user/result.txt"
            return self.result

    incomplete = SimpleNamespace(controller=FakeController(b"hello\n"))
    completed = SimpleNamespace(controller=FakeController(b"HELLO\n"))

    assert task.evaluate(incomplete) == 0.0
    assert task.evaluate(completed) == 1.0
