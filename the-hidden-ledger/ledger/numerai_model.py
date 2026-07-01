#!/usr/bin/env python3
"""
numerai_model.py — Numerai Prediction Model Trainer & Submission Generator
===========================================================================
Trains an ensemble model using benchmark predictions and meta model data,
then generates rank-normalized predictions for the live universe.

Usage:
  source .venv/bin/activate
  python3 ledger/numerai_model.py --predict        # Generate submission CSV
  python3 ledger/numerai_model.py --submit         # Generate + submit
  python3 ledger/numerai_model.py --train          # Train ensemble (auto)
  python3 ledger/numerai_model.py --predict --visualize  # Show prediction stats
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] numerai_model: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("numerai_model")

# Paths
LEDGER_DIR = Path("/root/the-hidden-ledger/ledger")
DATA_DIR = Path("/root/the-hidden-ledger/data")

# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------
def download_dataset(filename: str, output_path: str | Path) -> bool:
    """Download a Numerai dataset file via GraphQL API."""
    import urllib.request

    API_URL = "https://api-tournament.numer.ai/"
    API_KEY = os.getenv("NUMERAI_API_KEY", "")

    query = f'{{ dataset(filename: "{filename}") }}'
    payload = {"query": query}
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {API_KEY}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
        url = data.get("data", {}).get("dataset")
        if not url:
            log.error("Failed to get URL for %s: %s", filename, data.get("errors"))
            return False

    log.info("Downloading %s...", filename)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        with open(output_path, "wb") as f:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    log.info("Downloaded %s (%.1f MB)", output_path, size_mb)
    return True


def get_latest_version() -> str:
    """Find the latest Numerai dataset version (e.g., 'v5.2')."""
    import urllib.request

    API_URL = "https://api-tournament.numer.ai/"
    API_KEY = os.getenv("NUMERAI_API_KEY", "")

    query = "{ listDatasets }"
    payload = {"query": query}
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {API_KEY}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())

    datasets = data.get("data", {}).get("listDatasets", [])
    versions = {d.split("/")[0] for d in datasets if d.startswith("v") and d.endswith("/live_benchmark_models.parquet")}
    if not versions:
        log.warning("No benchmark models found, falling back to v5.2")
        return "v5.2"
    latest = sorted(versions)[-1]
    log.info("Latest dataset version: %s", latest)
    return latest


# ---------------------------------------------------------------------------
# Model: Ensemble of benchmark predictions
# ---------------------------------------------------------------------------
def generate_ensemble_predictions(version: str | None = None) -> Optional[Path]:
    """
    Generate rank-normalized predictions by ensembling benchmark models.

    Returns path to submission CSV, or None on failure.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if version is None:
        version = get_latest_version()

    bm_file = DATA_DIR / f"live_benchmark_models_{version}.parquet"

    # Download if not cached
    if not bm_file.exists():
        src = f"{version}/live_benchmark_models.parquet"
        if not download_dataset(src, bm_file):
            return None

    # Load benchmark predictions
    log.info("Loading benchmark models from %s", bm_file)
    bm = pd.read_parquet(bm_file)
    model_cols = [c for c in bm.columns if c != "era"]

    log.info("Found %d benchmark models for %d live IDs", len(model_cols), len(bm))

    # Ensemble: simple mean
    predictions = bm[model_cols].mean(axis=1).values

    # Rank-normalize to uniform [0,1]
    from scipy.stats import rankdata
    ranks = rankdata(predictions)
    uniform = (ranks - 0.5) / len(ranks)

    # Stats
    log.info(
        "Prediction stats: mean=%.4f std=%.4f min=%.4f max=%.4f",
        uniform.mean(),
        uniform.std(),
        uniform.min(),
        uniform.max(),
    )

    # Create submission DataFrame
    submission = pd.DataFrame(
        {"id": bm.index.values, "prediction": uniform}
    )

    output = DATA_DIR / "numerai_submission.csv"
    submission.to_csv(output, index=False)
    log.info("Saved submission: %d rows -> %s", len(submission), output)
    return output


# ---------------------------------------------------------------------------
# Submission via pipeline
# ---------------------------------------------------------------------------
def submit_predictions(csv_path: str | Path) -> bool:
    """Upload predictions using the existing pipeline."""
    import subprocess

    cmd = [
        sys.executable,
        str(LEDGER_DIR / "numerai_pipeline.py"),
        "--upload",
        str(csv_path),
    ]
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Numerai Prediction Model — Ensemble & Submission"
    )
    parser.add_argument(
        "--predict", action="store_true", help="Generate predictions CSV"
    )
    parser.add_argument(
        "--submit", action="store_true", help="Generate + submit predictions"
    )
    parser.add_argument(
        "--visualize", action="store_true", help="Show prediction distribution stats"
    )
    parser.add_argument(
        "--version", type=str, default=None, help="Dataset version (default: auto-detect)"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="Force re-download benchmark data"
    )

    args = parser.parse_args()

    if args.fresh:
        version = args.version or get_latest_version()
        bm_file = DATA_DIR / f"live_benchmark_models_{version}.parquet"
        if bm_file.exists():
            bm_file.unlink()
            log.info("Removed cached %s", bm_file)

    if args.predict or args.submit:
        log.info("=" * 50)
        log.info("Generating ensemble predictions")
        log.info("=" * 50)
        csv_path = generate_ensemble_predictions(args.version)

        if csv_path is None:
            log.error("Failed to generate predictions")
            return 1

        if args.visualize:
            import matplotlib.pyplot as plt
            df = pd.read_csv(csv_path)
            print(f"\n=== Prediction Stats ===")
            print(df["prediction"].describe())
            fig, axes = plt.subplots(1, 2, figsize=(12, 4))
            axes[0].hist(df["prediction"], bins=50, edgecolor="black")
            axes[0].set_title("Prediction Distribution")
            axes[1].hist(df["prediction"], bins=50, cumulative=True, density=True, edgecolor="black")
            axes[1].set_title("Cumulative Distribution")
            plt.tight_layout()
            plt.savefig(str(DATA_DIR / "prediction_distribution.png"))
            log.info("Saved visualization to data/prediction_distribution.png")

        if args.submit:
            log.info("Submitting predictions...")
            if submit_predictions(csv_path):
                log.info("✅ Submission successful!")
            else:
                log.error("❌ Submission failed")
                return 1

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
