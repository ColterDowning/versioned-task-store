"""
Implements the VersionedTaskStore class. Does the following:
    - Create a task. Importing a Python task file and an asset directory is sufficient.
    - Save a new immutable version after editing any part. Each version has a stable identifier.
    - List the task's history and **inspect** any version.
    - Restore an old version as the current version while preserving all saved versions.
    - Diff two versions. Show code and metadata changes, and identify added, removed, or changed assets.
    - Export any version as a Python task file with its assets.

"""
from pathlib import Path
import hashlib
import json
import shutil
import difflib
import re

class VersionedTaskStore:
    """This class implements all the required methods"""

    def __init__(self, storage_location: str | None = None):
        """Default storage location is in the repo folder"""

        if not storage_location:
            self.storage_location = Path(__file__).resolve().parent / "task-store"
        else:
            self.storage_location = Path(storage_location)

        self.storage_location = self.storage_location.resolve()
        self.storage_location.mkdir(parents=True, exist_ok=True)

    def save(self, task_name: str, working_directory: Path, message: str = "") -> int:
        """Saves all files in the working directory"""
        # Create a dir for the saved data to live
        blobs_directory = self.storage_location / "blobs"
        blobs_directory.mkdir(exist_ok=True)
        file_path_to_id = {} # relative path (str) -> file id (str)

        # Recursively iterate over all files in the working directory
        for file_path in working_directory.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(working_directory) # will be used for keeping names nice
                data = file_path.read_bytes()
                file_id = hashlib.sha256(data).hexdigest() # The hash of the file is its id

                blob_path = blobs_directory / file_id
                if not blob_path.exists(): # Prevent duplicating data, key to the design
                    blob_path.write_bytes(data)

                file_path_to_id[relative_path.as_posix()] = file_id

        # Create or load the task's edit history
        history_path = self.storage_location / "tasks" / task_name / "history.json"

        if history_path.exists():
            history = json.loads(history_path.read_text(encoding="utf-8"))
        else:
            history = {}

        # Check if this save has already been made
        for number, version in history.items(): # O(versions x files) check, but avoids the complexity of creating another hash map or hash version. Fine for a tool this size
            if version["files"] == file_path_to_id:
                return int(number)

        # If not, add to history
        version_number = len(history) + 1 

        history[str(version_number)] = {
            "message": message,
            "files": file_path_to_id
        }

        history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
        return version_number
        
    def create(self, working_directory: Path) -> str:
        """Creates a new task in storage from the given working directory"""
        # Confirm there is one task file
        task_files = list(working_directory.glob("task_*.py")) 
        task_files = [path for path in task_files if path.is_file()]

        if len(task_files) != 1:
            raise ValueError("Expected exactly one top level task_NNN.py file")

        # Create the task directory
        task_name = task_files[0].stem # task_NNN
        task_directory = self.storage_location / "tasks" / task_name

        if task_directory.exists():
            raise ValueError(f"Task already exists: {task_name}")

        task_directory.mkdir(parents=True)

        # Recursively save the contents
        self.save(task_name=task_name, working_directory=working_directory, message="Initial version")

        return task_name
        

    def history(self, task_name: str) -> dict:
        """Returns the dict containing the full history of the task"""
        history_path = self.storage_location / "tasks" / task_name / "history.json"
        return json.loads(history_path.read_text(encoding="utf-8")) # raises FileNotFoundError if history path not found

    def show(self, task_name: str, version_number: int, relative_path: str) -> bytes:
        history = self.history(task_name)
        version = history[str(version_number)]
        file_id = version["files"][relative_path]
        return (self.storage_location / "blobs" / file_id).read_bytes()

    def restore(self, task_name: str, version_number: int, working_directory: Path, force_restore: bool = False) -> None:
        history = self.history(task_name)
        version = history[str(version_number)]
        saved_files = version["files"]

        # Check that the saved contents are available before deleting anything in the working directory
        blobs_directory = self.storage_location / "blobs"
        for file_id in saved_files.values():
            blob_path = blobs_directory / file_id
            if not blob_path.is_file():
                raise FileNotFoundError(f"Missing blob: {file_id}")

        working_directory = working_directory.resolve()

        # Ensure that the passed working directory is not the store
        if (
            working_directory == self.storage_location
            or working_directory in self.storage_location.parents
            or self.storage_location in working_directory.parents
        ):
            raise ValueError("Working directory and storage must be separate")

        # Ensure there are no unsaved files before deleting (or require force restore)
        if not force_restore:
            current_files = {}
            for file_path in working_directory.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(working_directory)
                    current_files[relative_path.as_posix()] = hashlib.sha256(file_path.read_bytes()).hexdigest()

            if not any(
                entry["files"] == current_files
                for entry in history.values()
            ):
                raise ValueError(
                    "Working directory has unsaved changes. "
                    "Save them first or use force_restore=True"
                )

        working_directory.mkdir(parents=True, exist_ok=True)

        # Delete the contents of the working directory
        for path in working_directory.iterdir():
            if path.is_symlink() or not path.is_dir():
                path.unlink()
            else:
                shutil.rmtree(path)

        # Rebuild the selected version using copies of the blobs
        for relative_path, file_id in saved_files.items():
            destination = working_directory / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(blobs_directory / file_id, destination)


    def diff(self, task_name: str, old_version: int, new_version: int) -> dict:
        """Shows the code diff for the task_NNN.py file, and shows additions, deletions, and changes to assets"""
        # Get old and new paths to compare
        history = self.history(task_name)
        old_files = history[str(old_version)]["files"]
        new_files = history[str(new_version)]["files"]

        old_paths = set(old_files)
        new_paths = set(new_files)

        # Changes to files from old to new version
        added = sorted(new_paths - old_paths)
        removed = sorted(old_paths - new_paths)
        changed = sorted(
            path for path in old_paths & new_paths
            if old_files[path] != new_files[path] 
        )

        # Generate source file diff for task_NNN.py
        source_diffs = {}

        for path in sorted(set(added + removed + changed)):
            if not (
                "/" not in path
                and path.startswith("task_")
                and path.endswith(".py")
            ):
                continue # Don't generate diffs for assets

            old_source = (
                self.show(task_name, old_version, path).decode("utf-8")
                if path in old_files else ""
            )
            new_source = (
                self.show(task_name, new_version, path).decode("utf-8")
                if path in new_files else ""
            )

            source_diffs[path] = "\n".join(
                difflib.unified_diff(
                    old_source.splitlines(),
                    new_source.splitlines(),
                    fromfile=f"v{old_version}/{path}",
                    tofile=f"v{new_version}/{path}",
                    lineterm="",
                )
            )

        return {
            "added": added,
            "removed": removed,
            "changed": changed,
            "source_diffs": source_diffs
        }


    def export(self, task_name: str, version_number: int, output_directory: Path) -> None:
        history = self.history(task_name)
        saved_files = history[str(version_number)]["files"]

        # Require one top-level task_NNN.py file and assets under assets/
        task_files = [
            path for path in saved_files
            if re.fullmatch(r"task_[0-9]{3}\.py", path)
        ]
        if len(task_files) != 1:
            raise ValueError("Expected exactly one top-level task_NNN.py file")

        for relative_path in saved_files:
            path = Path(relative_path)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Invalid export path: {relative_path}")
            if relative_path != task_files[0] and not (
                len(path.parts) > 1 and path.parts[0] == "assets"
            ):
                raise ValueError(f"Expected an asset path: {relative_path}")

        # Confirm all blobs exist before writing the export
        blobs_directory = self.storage_location / "blobs"
        for file_id in saved_files.values():
            if not (blobs_directory / file_id).is_file():
                raise FileNotFoundError(f"Missing blob: {file_id}")

        # Require new or empty dir so the export contains only the saved files
        output_directory = output_directory.resolve()
        if output_directory.exists() and (
            not output_directory.is_dir()
            or any(output_directory.iterdir())
        ):
            raise ValueError("Export destination must be a new or empty directory")

        (output_directory / "assets").mkdir(parents=True, exist_ok=True)

        for relative_path, file_id in saved_files.items():
            destination = output_directory / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(blobs_directory / file_id, destination)


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        working_directory = root / "my-task"
        assets_directory = working_directory / "assets"
        assets_directory.mkdir(parents=True)
        (working_directory / "task_001.py").write_text(
            '# Sample source for testing save only.\ninstruction = "Sum the values."\n',
            encoding="utf-8",
        )
        asset_path = assets_directory / "input.csv"
        asset_path.write_text("value\n1\n2\n", encoding="utf-8")

        store = VersionedTaskStore(str(root / "task-store"))
        task_name = store.create(working_directory)
        history_path = store.storage_location / "tasks" / task_name / "history.json"
        history = json.loads(history_path.read_text(encoding="utf-8"))
        print("Created task:", task_name)
        print("Initial version:", next(iter(history)))
        assert task_name == "task_001"
        assert set(history) == {"1"}

        export_a = root / "export-A"
        store.export(task_name, 1, export_a)
        exported_a = {
            path.relative_to(export_a).as_posix(): path.read_bytes()
            for path in export_a.rglob("*")
            if path.is_file()
        }
        assert exported_a == {
            "task_001.py": (working_directory / "task_001.py").read_bytes(),
            "assets/input.csv": asset_path.read_bytes(),
        }

        unchanged = store.save(task_name, working_directory)

        asset_path.write_text("value\n1\n2\n3\n", encoding="utf-8")
        changed = store.save(task_name, working_directory, "Add another value")

        print("Unchanged save:", unchanged)
        print("Changed asset:", changed)
        assert (unchanged, changed) == (1, 2)
        print(history_path.read_text(encoding="utf-8"))

        for version_number in (1, 2):
            assert store.show(task_name, version_number, "task_001.py") == (
                working_directory / "task_001.py"
            ).read_bytes()

        original_asset = store.show(task_name, 1, "assets/input.csv")
        changed_asset = store.show(task_name, 2, "assets/input.csv")
        assert original_asset == b"value\n1\n2\n"
        assert changed_asset == b"value\n1\n2\n3\n"
        print("Version 1 asset:", original_asset)
        print("Version 2 asset:", changed_asset)

        for version_number, relative_path in (
            (99, "task_001.py"),
            (1, "assets/missing.csv"),
        ):
            try:
                store.show(task_name, version_number, relative_path)
            except KeyError:
                print("Expected KeyError:", version_number, relative_path)
            else:
                raise AssertionError("Expected KeyError for missing version or file")

        history_before_restore = history_path.read_bytes()
        store.restore(task_name, 1, working_directory)
        restored_files = {
            path.relative_to(working_directory).as_posix(): path.read_bytes()
            for path in working_directory.rglob("*")
            if path.is_file()
        }
        expected_files = {
            relative_path: store.show(task_name, 1, relative_path)
            for relative_path in store.history(task_name)["1"]["files"]
        }
        assert restored_files == expected_files
        print("Restored version 1: file paths and bytes match")

        export_b = root / "export-B"
        export_b.mkdir()
        store.export(task_name, 1, export_b)
        exported_b = {
            path.relative_to(export_b).as_posix(): path.read_bytes()
            for path in export_b.rglob("*")
            if path.is_file()
        }
        assert exported_a == exported_b == restored_files
        assert history_path.read_bytes() == history_before_restore
        assert store.show(task_name, 2, "assets/input.csv") == changed_asset
        print("Exports A and B have identical paths and bytes after restore")

        try:
            store.export(task_name, 2, export_a)
        except ValueError as error:
            assert "new or empty directory" in str(error)
            assert (export_a / "assets/input.csv").read_bytes() == original_asset
            print("Export refused a nonempty destination")
        else:
            raise AssertionError("Expected export to refuse a nonempty destination")

        (export_b / "assets/input.csv").write_bytes(b"Edited exported copy\n")
        assert store.show(task_name, 1, "assets/input.csv") == original_asset
        assert asset_path.read_bytes() == original_asset
        print("Editing an export leaves saved blobs and working files unchanged")

        asset_path.write_bytes(b"Unsaved changes\n")
        extra_path = assets_directory / "extra.txt"
        extra_path.write_bytes(b"Unsaved file\n")
        try:
            store.restore(task_name, 1, working_directory)
        except ValueError as error:
            assert "unsaved changes" in str(error)
            assert asset_path.read_bytes() == b"Unsaved changes\n"
            assert extra_path.read_bytes() == b"Unsaved file\n"
            print("Restore refused unsaved changes without deleting them")
        else:
            raise AssertionError("Expected restore to refuse unsaved changes")

        store.restore(task_name, 1, working_directory, force_restore=True)
        assert asset_path.read_bytes() == original_asset
        assert not extra_path.exists()
        assert history_path.read_bytes() == history_before_restore
        assert store.show(task_name, 2, "assets/input.csv") == changed_asset
        print("Forced restore discarded unsaved changes and preserved history")

        store.restore(task_name, 2, working_directory)
        assert asset_path.read_bytes() == changed_asset
        assert history_path.read_bytes() == history_before_restore
        print("Version 2 remains restorable")

        asset_diff = store.diff(task_name, 1, 2)
        assert asset_diff == {
            "added": [],
            "removed": [],
            "changed": ["assets/input.csv"],
            "source_diffs": {},
        }

        task_path = working_directory / "task_001.py"
        task_path.write_text(
            'instruction = "Sum the values excluding tax."\n'
            'def evaluate(env):\n'
            '    return 0.5\n',
            encoding="utf-8",
        )
        asset_path.unlink()
        (assets_directory / "reference.txt").write_text("Reference data\n", encoding="utf-8")
        third = store.save(task_name, working_directory, "Change source and replace asset")
        assert third == 3

        history_before_diff = history_path.read_bytes()
        source_before_diff = task_path.read_bytes()
        result = store.diff(task_name, 2, 3)
        assert result["added"] == ["assets/reference.txt"]
        assert result["removed"] == ["assets/input.csv"]
        assert result["changed"] == ["task_001.py"]
        source_diff = result["source_diffs"]["task_001.py"]
        assert '--- v2/task_001.py' in source_diff
        assert '+++ v3/task_001.py' in source_diff
        assert '-instruction = "Sum the values."' in source_diff
        assert '+instruction = "Sum the values excluding tax."' in source_diff
        assert '+def evaluate(env):' in source_diff
        assert '+    return 0.5' in source_diff
        assert store.diff(task_name, 3, 3) == {
            "added": [], "removed": [], "changed": [], "source_diffs": {},
        }
        assert history_path.read_bytes() == history_before_diff
        assert task_path.read_bytes() == source_before_diff
        print("Diff checks passed: assets, source changes, and identical versions")
        print(source_diff)
