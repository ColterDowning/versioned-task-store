[Taskstore_demo.webm](https://github.com/user-attachments/assets/eebc3976-2d97-4889-a353-f761fc3235f4)
# Versioned Task Store

A small tool for saving and recovering OSWorld task versions. The video above shows
the CLI tool executing the six-step workflow outlined in the assessment.md doc.

## Motivation

As engineers build tasks for AI agent evals, we need to edit and tweak the tasks during experimentation.
To ensure reliable testing, moving between task edits needs to be simple and reliable.

We want to build a tool that makes this easy. Essentially, we are building git for tasks.
The heart of this problem is to show solid, foundational engineering by making the tool super easy to use.

The easiest way an engineer (or agent) can manage versions is through a CLI. This implementation builds
a python class that can be used in traditional scripts and in a CLI form.

## User workflow

Below is an example workflow of how an engineer uses the tool.

Each task consists of a `task_NNN.py` file and an `assets/` directory. The Python
file contains a `BaseTask` subclass with metadata, setup code, and evaluator code,
and exposes that class as `TASK_CLASS` for OSWorld's loader.

```text
Engineer edits working files
    task_001.py + assets/
           |
           | save (through CLI -> VersionedTaskStore)
           v
    Immutable versions -------- export any version ------> task_NNN.py + assets/
           |                                                       |
           | restore                                               | load
           v                                                       v
    Working files                                               OSWorld
```

Example CLI commands:

```bash
taskstore --help
taskstore create ./expense-task
taskstore save task_001 -m "Adjust partial-credit scoring"
taskstore log task_001
taskstore show task_001 <version>
taskstore diff task_001 <version_1> <version_2>
taskstore restore task_001 <version>
taskstore export task_001 <version> ./exported-task
```

## Design

The VersionedTaskStore organizes tasks in the following structure:

```text
task-store/
  ├── blobs/
  │   ├── <sha256-of-file-content>
  │   ├── <sha256-of-file-content>
  │   └── ...
  └── tasks/
      ├── task_001/
      │   └── history.json
      └── task_002/
          └── history.json
```

Each task has its own version numbers. Its history.json contains:

```text
  {
    "1": {
      "message": "Initial version",
      "files": {
        "task_001.py": "<source-file-hash>",
        "assets/input.txt": "<original-asset-hash>"
      }
    },

    "2": {
      "message": "Switch to lowercase and update input",
      "files": {
        "task_001.py": "<updated-source-hash>",
        "assets/input.txt": "<updated-asset-hash>"
      }
    }
  }
```

blobs/ contains the raw bytes of the files that are saved, where the name 
of each blob is the hash of its bytes.

tasks/ stores different task names, and holds a version history for each.

history.json is indexed by version number for quick lookup on 'restore'. Within
each version, we keep the version commit message and a dict of all the files
in that version. The value of each file name in that dict is the byte hash of
the file, which is used to lookup the correct blob.

## Design Choices

The core design principle is:
The data structure must be kept as simple as possible, and any additions
must be strongly justified. Below are the main additions, with their 
explanations.

1. Separate blob storage. A simple but naive approach to the 'save' command
would be to copy all the files in the working directory to the storage
directory. While this works, task saves with the same files would duplicate
in storage. To avoid duplicates, we can hash the file contents and store it 
in a common dir, so before attempting to save, a quick existence check first
prevents duplication.

2. Separate history per task. Since each task gets its own history.json,
each task can get its own version numbers. This prevents versions from being
'intertwined' (ie. task_001 only has versions 1 and 3 because task_002
is using version 2).

3. Keeping the data structure as simple as possible. All the pieces that comprise
the storage data structure are kept minimal, which keeps the tool easy to use and 
understand. A tradeoff that is made is searching for existing saves to prevent
duplicates does not have its own hash and index. This trades O(1) lookup for 
O(versions x files), but is consciously made knowing the intended use of the tool.
A quick look at OSWorld 2.0 tasks shows the median number of files in assets/ is 5,
with a small std dev, and its reasonable to also assume the version count won't
increment to very large values either. This means the overwhelming amount of
time spent in 'save' is reading and hashing the files themselves, so the tradeoff
is only affecting a very small part of the function's total time, which
motivates the simpler design choice!


## Commands

As outlined in the problem statement, the tool has the following commands:

```code
create         Register and save a task
diff           Compare two saved task versions
export         Export a saved task version
log            List a task's saved versions
restore        Restore a saved task version
save           Save a task version
show           Inspect a saved version or file
```

command names use the git equivalent for familiarity, like log and show.

## Follow-up work

The next upgrade would be atomic saves, including failure rollback. The tool 
currently saves reliably, but rare disk failures could leave partial blobs.
This is fine for the vast majority of uses, but would benefit from the added
safety. A small amount of time should get this working easily.

## Installation and testing

In this repo, there are unit tests that cover the following:
1. The six step workflow outlined in the problem statement
2. OSWorld compatibility, including OSWorld's actual loader and BaseTask

There is also an integration test that runs a task in a real OSWorld desktop env.


From the repository root, install the CLI in your Python environment:

```bash
python -m pip install -e .
taskstore --help
```

By default, the saved tasks live in task-store/ beside storer.py.
Use "taskstore --store /path/to/store <command>" to set a custom storage location.

Install pytest and run the local tests:

```bash
python -m pip install pytest
python -m pytest -q tests/test_cli.py tests/test_storer.py
```

To show the six-step versioning demonstration:

```bash
python -m pytest -q -s tests/test_storer.py::test_required_versioning_workflow
```

These tests do not require an OSWorld installation or VM. For testing with a real
OSWorld environment, see [the integration test instructions](tests/
INTEGRATION.md).

