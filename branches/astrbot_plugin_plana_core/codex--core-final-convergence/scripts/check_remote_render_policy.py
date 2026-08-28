from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.task_session_support import TaskSessionSupportMixin


class SessionPolicy(TaskSessionSupportMixin):
    pass


def main() -> int:
    policy = SessionPolicy()
    short = {
        "status": "succeeded",
        "result": {
            "result_summary": "201到202联通正常",
            "duration_seconds": 4,
            "artifacts": [
                {
                    "name": "runner-output.txt",
                    "content_type": "text/plain",
                    "bytes": 20,
                }
            ],
        },
    }
    assert policy._remote_render_document(short) is None
    multi = {
        "status": "succeeded",
        "result": {
            "result_summary": "生成了两个文件。",
            "artifacts": [
                {"name": "a.txt", "content_type": "text/plain"},
                {"name": "b.txt", "content_type": "text/plain"},
            ],
        },
    }
    assert policy._remote_render_document(multi)["template"] == "task_result"
    image = {
        "status": "succeeded",
        "result": {
            "result_summary": "二维码已生成。",
            "artifacts": [{"name": "qr.png", "content_type": "image/png"}],
        },
    }
    assert policy._remote_render_document(image)["template"] == "task_result"
    print("remote_render_policy_check=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
