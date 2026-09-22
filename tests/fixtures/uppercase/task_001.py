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
