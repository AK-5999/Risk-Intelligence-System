from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def setup_logger(base_dir: Path) -> tuple[logging.Logger, str]:
    """
    Create a new log file for every pipeline run.

    Returns:
        logger: configured logger instance
        run_id: unique run identifier
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    log_dir = base_dir / "logger"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"run_{run_id}.log"

    logger = logging.getLogger(f"risk_pipeline_{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = logging.FileHandler(
        log_file,
        mode="w",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    logger.info("PIPELINE | run_id=%s | STARTED", run_id)
    logger.info("PIPELINE | log_file=%s", log_file)

    return logger, run_id