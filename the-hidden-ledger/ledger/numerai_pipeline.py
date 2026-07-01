#!/usr/bin/env python3
"""
numerai_pipeline.py — Numerai Gate 0: Submission & Authentication Engine
========================================================================
Part of Phase 2 Multi-Layer Security & Detonation Gates.

Handles:
  - Numerai WCP authentication (Gate 0)
  - Inference file validation via compliance.py (Gate 1 - callout)
  - Prediction upload and submission management (3-step flow)
  - Round-aware scheduling

3-Step Submission Flow:
  1. submissionUploadAuth GraphQL query → presigned S3 URL
  2. PUT predictions CSV to S3 presigned URL
  3. create_submission GraphQL mutation → submission ID

Environment:
  NUMERAI_API_KEY      — Full key (public_id$secret_key)
  NUMERAI_PUBLIC_ID    — Public ID portion
  NUMERAI_SECRET_KEY   — Secret key portion
  NUMERAI_MODEL_ID     — UUID of the model
  NUMERAI_USERNAME     — Numerai account username
  NUMERAI_TOURNAMENT   — Tournament number (8=Classic, 11=Signals, 12=CryptoSignals)

API:
  https://api-tournament.numer.ai/  (GraphQL)
  Auth: Authorization: Token <NUMERAI_API_KEY>
"""

from __future__ import annotations

import os
import csv
import json
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] numerai_pipeline: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("numerai_pipeline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL = "https://api-tournament.numer.ai/"
MODEL_ID = os.getenv("NUMERAI_MODEL_ID", "")
API_KEY = os.getenv("NUMERAI_API_KEY", "")
PUBLIC_ID = os.getenv("NUMERAI_PUBLIC_ID", "")
SECRET_KEY = os.getenv("NUMERAI_SECRET_KEY", "")
USERNAME = os.getenv("NUMERAI_USERNAME", "papimashala")
TOURNAMENT = int(os.getenv("NUMERAI_TOURNAMENT", "8"))

# Paths within the sprite ecosystem
DATA_DIR = Path("/root/the-hidden-ledger/data")
LEDGER_DIR = Path("/root/the-hidden-ledger/ledger")

# ---------------------------------------------------------------------------
# GraphQL helper
# ---------------------------------------------------------------------------
def _gql_raw(
    query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Execute a GraphQL query against the Numerai Tournament API."""
    if not API_KEY:
        return {"errors": [{"message": "NUMERAI_API_KEY is not set"}]}

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    req = Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {API_KEY}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        },
    )

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            if "errors" in data:
                for err in data["errors"]:
                    log.error("GraphQL error: %s", err.get("message"))
            return data
    except URLError as e:
        log.error("API request failed: %s", e)
        return {"errors": [{"message": str(e)}]}
    except json.JSONDecodeError as e:
        log.error("JSON decode error: %s", e)
        return {"errors": [{"message": str(e)}]}


# ---------------------------------------------------------------------------
# Authentication (Gate 0)
# ---------------------------------------------------------------------------
def authenticate() -> bool:
    """
    Gate 0: Numerai WCP Authentication.
    Verifies the API key is valid by fetching account details.
    Returns True if authenticated, False otherwise.
    """
    log.info("Gate 0: Authenticating with Numerai API...")
    result = _gql_raw("""
        query {
            account {
                username
                email
                status
            }
        }
    """)

    if "errors" in result and result["errors"]:
        log.error("Gate 0 FAILED: %s", result["errors"][0].get("message"))
        return False

    account = result.get("data", {}).get("account")
    if account and account.get("username"):
        log.info(
            "Gate 0 PASSED — Authenticated as %s (%s) [%s]",
            account["username"],
            account.get("email", "unknown"),
            account.get("status", "unknown"),
        )
        return True

    log.error("Gate 0 FAILED: No account data returned")
    return False


# ---------------------------------------------------------------------------
# Current round information
# ---------------------------------------------------------------------------
def get_current_round() -> Optional[dict[str, Any]]:
    """Fetch the current Numerai tournament round."""
    # Fetch the latest round (list is sorted descending)
    result = _gql_raw("""
        query {
            rounds {
                number
                closeTime
                scoreTime
            }
        }
    """)
    rounds = result.get("data", {}).get("rounds", [])
    # The API returns rounds in descending order with the latest round first
    if rounds:
        latest = rounds[0]
        log.info("Current round: %d (closes %s)", latest["number"], latest.get("closeTime", "?"))
        return latest
    return None


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------
def get_models() -> list[dict[str, Any]]:
    """List all models on the account."""
    result = _gql_raw("""
        query {
            account {
                models {
                    id
                    name
                }
            }
        }
    """)
    return result.get("data", {}).get("account", {}).get("models", [])


# ---------------------------------------------------------------------------
# 3-Step Submission Upload
# ---------------------------------------------------------------------------
def get_upload_auth(
    filename: str,
    tournament: int = 8,
    model_id: str | None = None,
) -> Optional[dict[str, str]]:
    """
    Step 1: Get a presigned S3 URL for uploading a submission CSV.
    Returns dict with 'filename' and 'url' keys, or None on failure.
    """
    model_id = model_id or MODEL_ID
    result = _gql_raw("""
        query($filename: String! $tournament: Int! $modelId: String) {
            submissionUploadAuth(
                filename: $filename
                tournament: $tournament
                modelId: $modelId
            ) {
                filename
                url
            }
        }
    """, {
        "filename": filename,
        "tournament": tournament,
        "modelId": model_id,
    })
    auth_data = result.get("data", {}).get("submissionUploadAuth")
    if auth_data:
        log.info("Got upload auth — filename=%s", auth_data["filename"])
        return auth_data
    log.error("Failed to get upload auth: %s", result.get("errors", "unknown"))
    return None


def upload_file_to_s3(url: str, file_path: str | Path) -> bool:
    """
    Step 2: Upload the CSV file to the presigned S3 URL.
    Returns True if upload succeeded (HTTP 200).
    """
    try:
        import requests as req_lib
        with open(file_path, "rb") as f:
            resp = req_lib.put(
                url,
                data=f.read(),
                headers={
                    "Content-Type": "text/csv",
                    "User-Agent": "sprite-cli/1.0",
                },
                timeout=600,
            )
        if resp.status_code == 200:
            log.info("S3 upload succeeded (HTTP 200)")
            return True
        log.error("S3 upload failed: HTTP %d", resp.status_code)
        return False
    except ImportError:
        log.error("requests library not available — cannot upload to S3")
        return False
    except Exception as e:
        log.error("S3 upload error: %s", e)
        return False


def create_submission_record(
    filename: str,
    tournament: int = 8,
    model_id: str | None = None,
    trigger_id: str | None = None,
    data_datestamp: int | None = None,
) -> Optional[str]:
    """
    Step 3: Create the submission record after the file is on S3.
    Returns the submission ID on success, or None on failure.
    """
    model_id = model_id or MODEL_ID
    result = _gql_raw("""
        mutation($filename: String!
                 $tournament: Int!
                 $modelId: String
                 $triggerId: String
                 $dataDatestamp: Int) {
            create_submission(
                filename: $filename
                tournament: $tournament
                modelId: $modelId
                triggerId: $triggerId
                source: "sprite-cli"
                dataDatestamp: $dataDatestamp
            ) {
                id
            }
        }
    """, {
        "filename": filename,
        "tournament": tournament,
        "modelId": model_id,
        "triggerId": trigger_id,
        "dataDatestamp": data_datestamp,
    })
    sub = result.get("data", {}).get("create_submission")
    if sub and sub.get("id"):
        sub_id = sub["id"]
        log.info("Submission created: %s", sub_id)
        return sub_id
    log.error("Failed to create submission: %s", result.get("errors", "unknown"))
    return None


def upload_predictions(
    file_path: str | Path,
    model_id: str | None = None,
    round_number: int | None = None,
) -> Optional[str]:
    """
    Upload a predictions CSV to Numerai for the specified model and round.

    3-step flow:
      1. Get presigned S3 upload URL via submissionUploadAuth
      2. PUT the CSV file to that S3 URL
      3. Call create_submission mutation to register

    Args:
        file_path: Path to the CSV file with predictions
        model_id: Model UUID (defaults to NUMERAI_MODEL_ID)
        round_number: Round number (defaults to current round, unused in auth)

    Returns:
        Submission ID string on success, or None on failure
    """
    model_id = model_id or MODEL_ID
    path = Path(file_path)
    if not path.exists():
        log.error("Predictions file not found: %s", path)
        return None

    log.info("Uploading predictions for model %s: %s", model_id, path)

    # Step 1: Get presigned upload URL
    auth = get_upload_auth(path.name, TOURNAMENT, model_id)
    if not auth:
        return None

    # Step 2: Upload file to S3
    if not upload_file_to_s3(auth["url"], path):
        return None

    # Step 3: Create submission record
    sub_id = create_submission_record(auth["filename"], TOURNAMENT, model_id)
    if not sub_id:
        return None

    # Log to execution ledger
    _append_ledger({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent": "quant-1",
        "action": "numerai.submission",
        "status": "ok",
        "model_id": model_id,
        "submission_id": sub_id,
        "file": str(path),
    })
    return sub_id


# ---------------------------------------------------------------------------
# Staking
# ---------------------------------------------------------------------------
def stake_model(
    model_id: str | None = None,
    value_nmr: float = 0.0,
) -> Optional[dict[str, Any]]:
    """Stake NMR on a model."""
    model_id = model_id or MODEL_ID
    if not model_id:
        log.error("No model ID for staking")
        return None

    result = _gql_raw("""
        mutation($modelId: String!, $value: Float!) {
            stake(modelId: $modelId, value: $value) {
                id
                status
            }
        }
    """, {"modelId": model_id, "value": value_nmr})
    return result.get("data", {}).get("stake")


# ---------------------------------------------------------------------------
# Submission status
# ---------------------------------------------------------------------------
def get_submission_status(submission_id: str) -> Optional[dict[str, Any]]:
    """Check the status of a submission."""
    result = _gql_raw("""
        query($modelId: String!) {
            submissions(modelId: $modelId) {
                id
                status
                round {
                    number
                }
                filename
                selected
            }
        }
    """, {"modelId": MODEL_ID})
    subs = result.get("data", {}).get("submissions", [])
    for s in subs:
        if s.get("id") == submission_id:
            return s
    if subs:
        log.info("Submission ID %s not in latest list — returning latest submission", submission_id)
        return subs[0]
    return None


# ---------------------------------------------------------------------------
# Execution ledger
# ---------------------------------------------------------------------------
def _append_ledger(entry: dict) -> None:
    """Append to the execution ledger JSONL."""
    ledger_path = LEDGER_DIR / "execution_ledger.jsonl"
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        log_path = LEDGER_DIR / "execution_ledger.log"
        with open(log_path, "a") as f:
            ts = entry.get("ts", "unknown")
            action = entry.get("action", "unknown")
            status = entry.get("status", "unknown")
            f.write(f"[{ts}] {action}: {status}\n")
    except Exception as e:
        log.warning("Could not write to ledger: %s", e)


# ---------------------------------------------------------------------------
# Full pipeline: Gate 0 -> compliance -> upload
# ---------------------------------------------------------------------------
def run_full_pipeline(
    predictions_csv: str | Path,
    model_id: str | None = None,
    skip_auth: bool = False,
) -> bool:
    """
    Run the complete Numerai submission pipeline.

    Steps:
      1. Gate 0: Authenticate with Numerai API
      2. Load & validate the predictions CSV
      3. (Gate 1 would call compliance.py here)
      4. Upload predictions (3-step flow)
      5. Log to execution_ledger

    Returns True on success.
    """
    log.info("=" * 60)
    log.info("Numerai Pipeline — Starting")
    log.info("=" * 60)

    # Step 1: Gate 0 Authentication
    if not skip_auth:
        if not authenticate():
            log.critical("Gate 0 FAILED — aborting pipeline")
            return False
    else:
        log.info("Gate 0: SKIPPED (skip_auth=True)")

    # Step 2: Check current round
    round_info = get_current_round()
    if round_info:
        close_time = round_info.get("closeTime", "unknown")
        log.info("Current round: %d (closes %s)", round_info["number"], close_time)
    else:
        log.warning("Could not determine current round")

    # Step 3: Validate predictions file
    path = Path(predictions_csv)
    if not path.exists():
        log.error("Predictions file not found: %s", path)
        return False

    try:
        with open(path, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if len(rows) < 2:
            log.error("CSV has no data rows")
            return False
        log.info("CSV validated: %d rows, %d columns", len(rows) - 1, len(rows[0]))
        log.info("Headers: %s", rows[0])
    except Exception as e:
        log.error("CSV validation failed: %s", e)
        return False

    # Step 4: Upload predictions
    log.info("Uploading predictions...")
    submission_id = upload_predictions(path, model_id)

    if submission_id:
        log.info("✅ Submission successful — ID: %s", submission_id)
        return True
    else:
        log.error("❌ Submission failed")
        _append_ledger({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "quant-1",
            "action": "numerai.submission",
            "status": "failed",
            "model_id": model_id or MODEL_ID,
            "file": str(path),
        })
        return False


# ---------------------------------------------------------------------------
# Live universe helpers
# ---------------------------------------------------------------------------
def get_live_example_preds() -> Optional[Path]:
    """
    Download the latest live_example_preds.csv to get all live universe IDs.
    Returns path to the downloaded file, or None on failure.
    """
    # Discover latest dataset version from listDatasets
    result = _gql_raw("{ listDatasets }")
    datasets = result.get("data", {}).get("listDatasets", [])
    # Find the latest v5.x live_example_preds.csv
    versions = set()
    for d in datasets:
        if d.startswith("v5.") and d.endswith("/live_example_preds.csv"):
            v = d.split("/")[0]
            versions.add(v)
    if not versions:
        log.error("No v5.x live example preds found")
        return None
    latest_ver = sorted(versions)[-1]
    filename = f"{latest_ver}/live_example_preds.csv"
    log.info("Downloading live universe from %s", filename)

    result = _gql_raw("""
        query($filename: String!) {
            dataset(filename: $filename)
        }
    """, {"filename": filename})
    url = result.get("data", {}).get("dataset")
    if not url:
        log.error("Failed to get dataset URL: %s", result.get("errors", "unknown"))
        return None

    output = DATA_DIR / f"live_example_preds_{latest_ver}.csv"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=120) as resp:
            with open(output, "wb") as f:
                f.write(resp.read())
        log.info("Downloaded live universe: %s (%d rows)", output, _csv_row_count(output))
        return output
    except Exception as e:
        log.error("Failed to download live universe: %s", e)
        return None


def _csv_row_count(path: Path) -> int:
    """Count data rows in a CSV file (excluding header)."""
    import csv
    with open(path) as f:
        return sum(1 for _ in csv.DictReader(f))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Numerai Gate 0: Submission & Authentication Pipeline"
    )
    parser.add_argument("--upload", type=str, help="Path to predictions CSV to upload")
    parser.add_argument("--auth-only", action="store_true", help="Just test authentication")
    parser.add_argument("--model", type=str, help="Model ID (default: NUMERAI_MODEL_ID)")
    parser.add_argument("--skip-auth", action="store_true", help="Skip Gate 0 auth")
    parser.add_argument("--status", type=str, help="Check submission status by ID")
    parser.add_argument("--stake", type=float, help="Stake NMR amount on model")
    parser.add_argument("--info", action="store_true", help="Print account & round info")
    parser.add_argument("--download-live", action="store_true", help="Download the latest live universe IDs")

    args = parser.parse_args()

    if args.auth_only:
        result = authenticate()
        print("Gate 0:", "✅ PASSED" if result else "❌ FAILED")
        return 0 if result else 1

    if args.status:
        result = get_submission_status(args.status)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Submission not found")
        return 0

    if args.stake is not None:
        result = stake_model(args.model, args.stake)
        print(json.dumps(result, indent=2) if result else "Staking failed")
        return 0 if result else 1

    if args.info:
        print(f"\n=== Numerai Account Info ===")
        print(f"Username: {USERNAME}")
        print(f"Model ID: {MODEL_ID}")
        print(f"Tournament: {TOURNAMENT}")
        auth_ok = authenticate()
        print(f"Auth: {'✅ OK' if auth_ok else '❌ FAILED'}")
        round_info = get_current_round()
        if round_info:
            print(f"Current Round: {round_info['number']}")
            print(f"  Closes:  {round_info.get('closeTime', 'N/A')}")
            print(f"  Scores:  {round_info.get('scoreTime', 'N/A')}")
        models = get_models()
        if models:
            print(f"\nModels ({len(models)}):")
            for m in models:
                print(f"  - {m['name']} ({m['id']})")
        return 0

    if args.download_live:
        result = get_live_example_preds()
        if result:
            print(f"Downloaded live universe: {result}")
            return 0
        return 1

    if args.upload:
        success = run_full_pipeline(args.upload, args.model, args.skip_auth)
        return 0 if success else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
