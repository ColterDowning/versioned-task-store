import argparse
import json
import sys
from pathlib import Path

from storer import VersionedTaskStore


class HelpFormatter(argparse.HelpFormatter):
    def _format_action(self, action):
        if isinstance(action, argparse._SubParsersAction):
            return "".join(self._format_action(command) for command in action._get_subactions())
        return super()._format_action(action)


def main():
    parser = argparse.ArgumentParser(prog="taskstore", formatter_class=HelpFormatter)
    parser.add_argument(
        "--store",
        help="Storage directory; defaults to task-store beside storer.py",
    )

    commands = parser.add_subparsers(
        dest="command", required=True, title="commands", metavar="COMMAND",
    )

    create_parser = commands.add_parser("create", help="Register and save a task")
    create_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="Task working directory; defaults to the current directory",
    )

    diff_parser = commands.add_parser("diff", help="Compare two saved task versions")
    diff_parser.add_argument("task", help="Registered task name")
    diff_parser.add_argument("old", type=int, help="Old version number")
    diff_parser.add_argument("new", type=int, help="New version number")

    export_parser = commands.add_parser("export", help="Export a saved task version")
    export_parser.add_argument("task", help="Registered task name")
    export_parser.add_argument("version", type=int, help="Saved version number")
    export_parser.add_argument(
        "output", type=Path, help="New or empty export directory",
    )

    log_parser = commands.add_parser("log", help="List a task's saved versions")
    log_parser.add_argument(
        "task", nargs="?", help="Registered task name; inferred from the current directory if omitted",
    )

    restore_parser = commands.add_parser("restore", help="Restore a saved task version")
    restore_parser.add_argument("task", help="Registered task name")
    restore_parser.add_argument("version", type=int, help="Saved version number")
    restore_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Task working directory; defaults to the current directory",
    )
    restore_parser.add_argument(
        "--force", action="store_true", help="Discard unsaved working-directory changes",
    )

    save_parser = commands.add_parser("save", help="Save a task version")
    save_parser.add_argument("task", help="Registered task name")
    save_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Task working directory; defaults to the current directory",
    )
    save_parser.add_argument("-m", "--message", default="", help="Version message")

    show_parser = commands.add_parser("show", help="Inspect a saved version or file")
    show_parser.add_argument("task", help="Registered task name")
    show_parser.add_argument("version", type=int, help="Saved version number")
    show_parser.add_argument("file", nargs="?", help="Relative path of a saved file")

    args = parser.parse_args()
    try:
        store = VersionedTaskStore(args.store)
    except OSError as error:
        parser.exit(1, f"Error: Could not initialize storage: {error}\n")

    if args.command != "create":
        try:
            if args.command == "log" and args.task is None:
                task_files = [path for path in Path.cwd().glob("task_*.py") if path.is_file()]
                if len(task_files) != 1:
                    raise ValueError("Expected exactly one top-level task_*.py file; supply a task name")
                args.task = task_files[0].stem
            history = store.history(args.task)
        except FileNotFoundError:
            parser.exit(1, f"Error: Task {args.task} not found\n")
        except (ValueError, OSError) as error:
            parser.exit(1, f"Error: {error}\n")

        versions = []
        if args.command in ("show", "restore", "export"):
            versions = [args.version]
        elif args.command == "diff":
            versions = [args.old, args.new]
        for number in versions:
            if str(number) not in history:
                parser.exit(1, f"Error: Version {number} not found for {args.task}\n")

        if args.command == "show" and args.file is not None:
            if args.file not in history[str(args.version)]["files"]:
                parser.exit(1, f"Error: File {args.file} not found in {args.task}, version {args.version}\n")

    if args.command == "create":
        try:
            task_name = store.create(args.path)
        except (ValueError, OSError) as error:
            parser.exit(1, f"Error: {error}\n")

        print(f"Created {task_name}, version 1")

    elif args.command == "save":
        if not args.path.is_dir():
            parser.exit(1, f"Error: Working directory not found or not a directory: {args.path}\n")
        if not (args.path / f"{args.task}.py").is_file():
            parser.exit(1, f"Error: Expected {args.task}.py in working directory: {args.path}. Run from the task folder or use --path.\n")
        try:
            version_number = store.save(args.task, args.path, args.message)
        except (ValueError, OSError) as error:
            parser.exit(1, f"Error: {error}\n")

        print(f"Saved {args.task}, version {version_number}")

    elif args.command == "log":
        print("Version  Message")
        for number in sorted(history, key=int):
            print(f"{number:<9}{history[number]['message']}")

    elif args.command == "show":
        try:
            if args.file is None:
                version = history[str(args.version)]
                print(json.dumps(version, indent=2))
            else:
                data = store.show(args.task, args.version, args.file)
                sys.stdout.buffer.write(data)
        except (KeyError, ValueError, OSError) as error:
            parser.exit(1, f"Error: {error}\n")

    elif args.command == "restore":
        try:
            store.restore(args.task, args.version, args.path, force_restore=args.force)
        except (KeyError, ValueError, OSError) as error:
            parser.exit(1, f"Error: {error}\n")

        print(f"Restored {args.task}, version {args.version}")

    elif args.command == "diff":
        try:
            result = store.diff(args.task, args.old, args.new)
        except (KeyError, ValueError, OSError) as error:
            parser.exit(1, f"Error: {error}\n")

        print(f"{args.task}: version {args.old} -> version {args.new}")
        if not any(result[status] for status in ("added", "removed", "changed")):
            print("No changes")
        else:
            for status in ("added", "removed", "changed"):
                for path in result[status]:
                    print(f"{status:<9}{path}")
            for source_diff in result["source_diffs"].values():
                print(source_diff)

    elif args.command == "export":
        try:
            store.export(args.task, args.version, args.output)
        except (KeyError, ValueError, OSError) as error:
            parser.exit(1, f"Error: {error}\n")

        print(f"Exported {args.task}, version {args.version} to {args.output}")


if __name__ == "__main__":
    main()
