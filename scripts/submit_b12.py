#!/usr/bin/env python3
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SUBMISSION_URL = "https://b12.io/apply/submission"


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def build_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_default_repo_link() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    return f"{server}/{repo}" if repo else ""


def build_default_action_run_link() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def canonical_json_bytes(payload: dict) -> bytes:
    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return body.encode("utf-8")


def compute_signature(secret: str, body_bytes: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def submit_application() -> int:
    try:
        payload = {
            "action_run_link": os.environ.get("ACTION_RUN_LINK", "").strip() or build_default_action_run_link(),
            "email": required_env("APPLICANT_EMAIL"),
            "name": required_env("APPLICANT_NAME"),
            "repository_link": os.environ.get("REPOSITORY_LINK", "").strip() or build_default_repo_link(),
            "resume_link": required_env("RESUME_LINK"),
            "timestamp": build_timestamp(),
        }
        missing_payload_fields = [k for k, v in payload.items() if not v]
        if missing_payload_fields:
            raise ValueError(f"Missing required payload fields: {', '.join(missing_payload_fields)}")

        signing_secret = required_env("B12_SIGNING_SECRET")
        body_bytes = canonical_json_bytes(payload)
        signature = compute_signature(signing_secret, body_bytes)

        request = Request(
            SUBMISSION_URL,
            data=body_bytes,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Signature-256": signature,
            },
        )

        with urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
            status_code = response.getcode()

        if status_code != 200:
            print(f"Submission failed with status {status_code}: {response_body}", file=sys.stderr)
            return 1

        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError:
            print(f"Expected JSON response, got: {response_body}", file=sys.stderr)
            return 1

        receipt = parsed.get("receipt")
        if not receipt:
            print(f"No receipt found in response: {response_body}", file=sys.stderr)
            return 1

        print(receipt)
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTPError {exc.code}: {body}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(submit_application())
