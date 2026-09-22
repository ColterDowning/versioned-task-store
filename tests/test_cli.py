from pathlib import Path
import json
import subprocess
import sys

import pytest

from storer import VersionedTaskStore


@pytest.fixture
def cli(tmp_path):
    working = tmp_path / "working"
    (working / "assets").mkdir(parents=True)
    (working / "task_001.py").write_bytes(b'instruction = "Original"\n')
    (working / "assets" / "input.bin").write_bytes(b"\x00\xfforiginal")
    store = VersionedTaskStore(str(tmp_path / "store"))
    script = Path(__file__).resolve().parents[1] / "taskstore_cli.py"

    def run(*args, cwd=working):
        return subprocess.run(
            [sys.executable, "-B", str(script), "--store", str(store.storage_location), *args],
            cwd=cwd,
            capture_output=True,
        )

    return run, working, store


def test_create(cli):
    run, working, store = cli
    result = run("create", str(working))
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"Created task_001, version 1\n"
    assert set(store.history("task_001")) == {"1"}
    assert run("create").returncode == 1


def test_save(cli):
    run, working, store = cli
    store.create(working)
    (working / "assets" / "input.bin").write_bytes(b"changed")
    result = run("save", "task_001", "-m", "Changed input")
    assert result.returncode == 0, result.stderr
    assert store.history("task_001")["2"]["message"] == "Changed input"
    assert store.show("task_001", 2, "assets/input.bin") == b"changed"
    invalid = run("save", "task_001", "--path", "missing")
    assert invalid.returncode == 1
    assert b"Working directory not found or not a directory" in invalid.stderr
    assert set(store.history("task_001")) == {"1", "2"}


def test_save_rejects_assets_directory(cli):
    run, working, store = cli
    store.create(working)
    history = store.history("task_001")
    (working / "assets" / "input.bin").write_bytes(b"unsaved")
    for result in (
        run("save", "task_001", cwd=working / "assets"),
        run("save", "task_001", "--path", "assets"),
    ):
        assert result.returncode == 1
        assert b"Expected task_001.py in working directory" in result.stderr
        assert b"--path" in result.stderr
    assert store.history("task_001") == history
    assert (working / "assets" / "input.bin").read_bytes() == b"unsaved"


def test_log(cli):
    run, working, store = cli
    store.create(working)
    result = run("log")
    assert result.returncode == 0, result.stderr
    assert b"Version  Message" in result.stdout
    assert b"1        Initial version" in result.stdout
    assert run("log", "task_001").stdout == result.stdout
    missing = run("log", "missing")
    assert missing.returncode == 1
    assert missing.stderr == b"Error: Task missing not found\n"


def test_show(cli):
    run, working, store = cli
    store.create(working)
    details = run("show", "task_001", "1")
    assert details.returncode == 0, details.stderr
    assert json.loads(details.stdout) == store.history("task_001")["1"]
    result = run("show", "task_001", "1", "assets/input.bin")
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"\x00\xfforiginal"
    missing = run("show", "task_001", "1", "missing.txt")
    assert missing.returncode == 1
    assert missing.stderr == b"Error: File missing.txt not found in task_001, version 1\n"


def test_restore(cli):
    run, working, store = cli
    store.create(working)
    asset = working / "assets" / "input.bin"
    asset.write_bytes(b"unsaved")
    refused = run("restore", "task_001", "1")
    assert refused.returncode == 1
    assert b"unsaved changes" in refused.stderr
    assert asset.read_bytes() == b"unsaved"
    result = run("restore", "task_001", "1", "--force")
    assert result.returncode == 0, result.stderr
    assert asset.read_bytes() == b"\x00\xfforiginal"


def test_diff(cli):
    run, working, store = cli
    store.create(working)
    (working / "task_001.py").write_bytes(b'instruction = "Updated"\n')
    store.save("task_001", working)
    result = run("diff", "task_001", "1", "2")
    assert result.returncode == 0, result.stderr
    assert b"changed  task_001.py" in result.stdout
    assert b'-instruction = "Original"' in result.stdout
    assert b'+instruction = "Updated"' in result.stdout
    assert b"No changes" in run("diff", "task_001", "1", "1").stdout


def test_export(cli, tmp_path):
    run, working, store = cli
    store.create(working)
    output = tmp_path / "export"
    result = run("export", "task_001", "1", str(output))
    assert result.returncode == 0, result.stderr
    for relative_path in ("task_001.py", "assets/input.bin"):
        assert (output / relative_path).read_bytes() == (working / relative_path).read_bytes()
    refused = run("export", "task_001", "1", str(output))
    assert refused.returncode == 1
    assert b"new or empty directory" in refused.stderr
