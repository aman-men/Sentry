"""Partition the detector training dataset into deterministic client splits."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.model_selection import StratifiedKFold

try:
    from detector.model import load_data
except ImportError:
    from model import load_data

DEFAULT_CLIENT_COUNT = 3
DEFAULT_SEED = 42


def client_data_dir(base_dir: str | Path | None = None) -> Path:
    if base_dir:
        root = Path(base_dir)
        return root if root.name == "client_data" else root / "client_data"
    return Path(__file__).resolve().parent / "client_data"


def partition_training_data(
    client_count: int = DEFAULT_CLIENT_COUNT,
    seed: int = DEFAULT_SEED,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """Split the detector train set into client CSVs stratified by risk level."""
    if client_count < 2:
        raise ValueError("Federated partitioning requires at least 2 clients.")

    train_df = load_data()["train"].copy()
    destination = client_data_dir(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    splitter = StratifiedKFold(n_splits=client_count, shuffle=True, random_state=seed)
    paths: list[Path] = []

    for client_index, (_, client_indices) in enumerate(
        splitter.split(train_df["text"], train_df["risk_level"]),
        start=1,
    ):
        client_df = train_df.iloc[client_indices].reset_index(drop=True)
        path = destination / f"client_{client_index}.csv"
        client_df.to_csv(path, index=False)
        paths.append(path)

    return paths


def partitions_exist(
    client_count: int = DEFAULT_CLIENT_COUNT, output_dir: str | Path | None = None
) -> bool:
    destination = client_data_dir(output_dir)
    return all((destination / f"client_{index}.csv").exists() for index in range(1, client_count + 1))
