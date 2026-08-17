from __future__ import annotations

import os
from pathlib import Path

from dotenv import (
    load_dotenv,
)

from src.logging_config import (
    setup_logger,
)
from src.risk_analyzer import (
    RiskAnalyzer,
)
from src.risk_candidate_extractor import (
    RiskCandidateExtractor,
)
from src.risk_generator import (
    RiskGenerator,
)
from src.validator import (
    RiskValidator,
)


def main() -> None:

    load_dotenv()

    base_dir = (
        Path(__file__)
        .resolve()
        .parent
    )

    # ==================================================================
    # PATHS
    # ==================================================================

    parsed_input_path = (
        base_dir
        / "InputJson"
        / "VestasAnnualReport2025.json"
    )

    risk_analysis_path = (
        base_dir
        / "output"
        / "risk_analysis.json"
    )

    candidate_output_path = (
        base_dir
        / "output"
        / "risk_candidates.json"
    )

    raw_generation_path = (
        base_dir
        / "output"
        / "raw_generation.json"
    )

    final_output_path = (
        base_dir
        / "output"
        / "final_risks.json"
    )

    prompt_path = (
        base_dir
        / "prompts"
        / "prompts.json"
    )

    # ==================================================================
    # CONFIG
    # ==================================================================

    prompt_name = os.getenv(
        "RISK_PROMPT_NAME",
        "risk_extraction",
    )

    prompt_version = os.getenv(
        "RISK_PROMPT_VERSION",
        "2.0",
    )

    # ==================================================================
    # LOGGER
    # ==================================================================

    logger, run_id = (
        setup_logger(
            base_dir
        )
    )

    try:

        # ==============================================================
        # STEP 1
        # Risk Analysis / hierarchy reconstruction
        # ==============================================================

        logger.info(
            "PIPELINE | run_id=%s | STEP_1 | STARTED",
            run_id,
        )

        analyzer = (
            RiskAnalyzer(
                input_path=(
                    parsed_input_path
                ),
                logger=logger,
            )
        )

        analysis = (
            analyzer.analyze()
        )

        analyzer.save(
            data=analysis,
            output_path=(
                risk_analysis_path
            ),
        )

        logger.info(
            "PIPELINE | run_id=%s | STEP_1 | SUCCESS",
            run_id,
        )

        # ==============================================================
        # STEP 1.5
        # Deterministic candidate extraction
        # ==============================================================

        logger.info(
            "PIPELINE | run_id=%s | STEP_1_5 | STARTED",
            run_id,
        )

        candidate_extractor = (
            RiskCandidateExtractor(
                input_path=(
                    risk_analysis_path
                ),
                logger=logger,
            )
        )

        candidate_data = (
            candidate_extractor.extract()
        )

        candidate_extractor.save(
            data=candidate_data,
            output_path=(
                candidate_output_path
            ),
        )

        logger.info(
            "PIPELINE | run_id=%s | STEP_1_5 | SUCCESS",
            run_id,
        )

        # ==============================================================
        # STEP 2
        # LLM semantic generation
        # ==============================================================

        logger.info(
            "PIPELINE | run_id=%s | STEP_2 | STARTED",
            run_id,
        )

        generator = (
            RiskGenerator(
                input_path=(
                    candidate_output_path
                ),
                prompt_path=(
                    prompt_path
                ),
                prompt_name=(
                    prompt_name
                ),
                prompt_version=(
                    prompt_version
                ),
                logger=logger,
            )
        )

        generated = (
            generator.generate()
        )

        generator.save(
            data=generated,
            output_path=(
                raw_generation_path
            ),
        )

        logger.info(
            "PIPELINE | run_id=%s | STEP_2 | SUCCESS",
            run_id,
        )

        # ==============================================================
        # STEP 3
        # Structural / grounding validation
        # ==============================================================

        logger.info(
            "PIPELINE | run_id=%s | STEP_3 | STARTED",
            run_id,
        )

        validator = (
            RiskValidator(
                parsed_input_path=(
                    parsed_input_path
                ),
                logger=logger,
            )
        )

        validated = (
            validator.validate(
                generated
            )
        )

        validator.save(
            output=validated,
            output_path=(
                final_output_path
            ),
        )

        logger.info(
            "PIPELINE | run_id=%s | STEP_3 | SUCCESS",
            run_id,
        )

        logger.info(
            "PIPELINE | run_id=%s | COMPLETED | "
            "final_output=%s",
            run_id,
            final_output_path,
        )

    except Exception:

        logger.exception(
            "PIPELINE | run_id=%s | FAILED",
            run_id,
        )

        raise


if __name__ == "__main__":
    main()