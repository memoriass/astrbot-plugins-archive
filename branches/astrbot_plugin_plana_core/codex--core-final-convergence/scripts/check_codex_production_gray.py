from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from typing import Any
import urllib.error
import urllib.request
import uuid


class GraySuite:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.cases: list[dict[str, Any]] = []

    def record(self, name: str, passed: bool, detail: object = "") -> None:
        self.cases.append({"name": name, "passed": bool(passed), "detail": detail})

    def request(
        self,
        method: str,
        path: str,
        payload: object | None = None,
        *,
        raw: bytes | None = None,
        authorized: bool = True,
    ) -> tuple[int, dict[str, Any], bytes, dict[str, str]]:
        data = raw
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if authorized and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                return response.status, _json_object(body), body, response_headers
        except urllib.error.HTTPError as exc:
            body = exc.read()
            response_headers = {key.lower(): value for key, value in exc.headers.items()}
            return exc.code, _json_object(body), body, response_headers

    def delegate(self, title: str, *, lane: str = "interactive", **extra: Any) -> str:
        payload = {
            "request_id": f"gray-{uuid.uuid4().hex}",
            "title": title,
            "text": title,
            "lane": lane,
            **extra,
        }
        status, body, _, _ = self.request("POST", "/plana/codex/delegate", payload)
        if status != 202 or not body.get("run_id"):
            raise RuntimeError(f"delegate_failed:{status}:{body}")
        return str(body["run_id"])

    def wait(self, run_id: str, timeout: int = 240) -> dict[str, Any]:
        deadline = time.time() + timeout
        latest: dict[str, Any] = {}
        while time.time() < deadline:
            status, body, _, _ = self.request(
                "GET", f"/plana/codex/result/{run_id}"
            )
            if status == 200 and isinstance(body.get("result"), dict):
                latest = body["result"]
                if latest.get("status") in {"succeeded", "failed", "cancelled"}:
                    return latest
            time.sleep(1)
        raise TimeoutError(f"gray_wait_timeout:{run_id}:{latest.get('status')}")

    def run(self) -> dict[str, Any]:
        status, health, _, _ = self.request("GET", "/health", authorized=False)
        self.record("01_health_http_200", status == 200, status)
        self.record("02_health_executes_tasks", health.get("executes_tasks") is True)
        self.record("03_health_interactive_worker", health.get("workers", {}).get("interactive") == 1)
        self.record("04_health_long_worker", health.get("workers", {}).get("long") == 1)
        self.record("05_health_allowlist", "192.168.1.201" in health.get("allowed_clients", []))

        status, body, _, _ = self.request("GET", "/status", authorized=False)
        self.record(
            "06_status_uses_lan_allowlist",
            status == 200 and body.get("auth_model") == "lan_allowlist",
            status,
        )
        status, body, _, _ = self.request("GET", "/status")
        self.record("07_status_authorized", status == 200 and body.get("ok") is True, status)
        status, body, _, _ = self.request("GET", "/plana/codex/result/missing")
        self.record("08_missing_result_404", status == 404 and body.get("error") == "not_found")
        status, body, _, _ = self.request("POST", "/plana/codex/cancel/missing", {})
        self.record("09_missing_cancel_404", status == 404 and body.get("error") == "not_found")
        status, body, _, _ = self.request("POST", "/plana/codex/delegate", raw=b"{")
        self.record("10_invalid_json_rejected", status == 400 and body.get("error") == "invalid_json")
        status, body, _, _ = self.request("POST", "/plana/codex/delegate", payload=[])
        self.record("11_non_object_rejected", status == 400 and body.get("error") == "payload_must_be_object")
        for number, lane in ((12, "high_isolation"), (13, "import")):
            status, body, _, _ = self.request(
                "POST",
                "/plana/codex/delegate",
                {"request_id": f"gray-disabled-{lane}", "title": "disabled", "lane": lane},
            )
            self.record(
                f"{number:02d}_{lane}_disabled",
                status == 409 and body.get("error") == "lane_disabled",
                body,
            )

        empty_id = self.delegate("", lane="interactive")
        empty_result = self.wait(empty_id, 90)
        self.record("14_empty_query_fails", empty_result.get("status") == "failed", empty_result.get("error"))
        bad_ref_id = self.delegate(
            "Reply exactly denied", lane="interactive", service_refs=["unregistered.service"]
        )
        bad_ref_result = self.wait(bad_ref_id, 90)
        self.record(
            "15_unregistered_service_ref_fails",
            bad_ref_result.get("status") == "failed"
            and "service_ref_not_allowed" in str(bad_ref_result.get("error")),
            bad_ref_result.get("error"),
        )

        short_id = self.delegate("Reply with exactly: codex-gray-ok", lane="interactive")
        short_result = self.wait(short_id, 120)
        summary = str(short_result.get("result_summary") or "")
        self.record("16_short_task_succeeds", short_result.get("status") == "succeeded", short_result.get("error"))
        self.record("17_short_task_real_text", "codex-gray-ok" in summary.casefold(), summary[:160])
        self.record("18_short_task_executes_true", short_result.get("executes_tasks") is True)
        self.record("19_short_task_timestamps", bool(short_result.get("started_at") and short_result.get("finished_at")))
        short_artifacts = short_result.get("artifacts") or []
        self.record("20_short_task_artifact_metadata", bool(short_artifacts), short_artifacts)
        if short_artifacts:
            artifact = short_artifacts[0]
            status, _, raw, headers = self.request(
                "GET", f"/plana/codex/artifact/{short_id}/{artifact.get('artifact_id')}"
            )
            actual_hash = hashlib.sha256(raw).hexdigest()
            self.record("21_artifact_download", status == 200 and bool(raw), status)
            self.record("22_artifact_hash", actual_hash == artifact.get("sha256"), actual_hash)
            self.record(
                "23_artifact_header_hash",
                headers.get("x-plana-artifact-sha256") == artifact.get("sha256"),
            )
        else:
            for number, name in ((21, "artifact_download"), (22, "artifact_hash"), (23, "artifact_header_hash")):
                self.record(f"{number:02d}_{name}", False, "missing_artifact")

        long_prompt = (
            "Create two small UTF-8 files under gray-test in the current workspace only: "
            "summary.txt containing 'gray summary' and checklist.txt containing 'gray checklist'. "
            "Then return both relative paths as artifacts. Do not modify anything else."
        )
        long_id = self.delegate(long_prompt, lane="long")
        long_result = self.wait(long_id, 240)
        long_artifacts = long_result.get("artifacts") or []
        self.record("24_long_task_terminal", long_result.get("status") in {"succeeded", "failed"}, long_result.get("error"))
        self.record("25_long_task_succeeds", long_result.get("status") == "succeeded", long_result.get("error"))
        self.record("26_multi_artifact", len(long_artifacts) >= 2, long_artifacts)

        first_id = self.delegate("Reply exactly first-queued-test", lane="interactive")
        second_id = self.delegate("Reply exactly second-queued-test", lane="interactive")
        status, cancel_body, _, _ = self.request(
            "POST", f"/plana/codex/cancel/{second_id}", {}
        )
        second_result = self.wait(second_id, 120)
        first_result = self.wait(first_id, 120)
        self.record("27_cancel_endpoint_accepts", status in {200, 202}, cancel_body)
        self.record("28_cancel_reaches_terminal", second_result.get("status") == "cancelled", second_result)
        self.record("29_parallel_first_completes", first_result.get("status") == "succeeded", first_result.get("error"))
        status, final_status, _, _ = self.request("GET", "/status")
        lanes = final_status.get("lanes", {})
        stable = all(int(values.get("running", 0)) == 0 for values in lanes.values())
        self.record("30_no_stuck_running_tasks", status == 200 and stable, lanes)

        passed = sum(1 for case in self.cases if case["passed"])
        return {
            "total": len(self.cases),
            "passed": passed,
            "failed": len(self.cases) - passed,
            "cases": self.cases,
        }


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the 30-case Codex production gray suite.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--output")
    args = parser.parse_args()
    token = os.getenv("PLANA_CODEX_RUNNER_TOKEN", "")
    result = GraySuite(args.base_url, token).run()
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    print(payload)
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
