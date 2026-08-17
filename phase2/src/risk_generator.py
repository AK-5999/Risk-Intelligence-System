from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.category_resolver import (
    CategoryResolver,
)
from src.llm_client import (
    OpenRouterClient,
)
from src.schemas import (
    GeneratedRiskBatch,
)


class PromptStore:
    """
    Versioned JSON prompt store.
    """

    def __init__(
        self,
        prompt_path: Path,
    ):
        self.prompt_path = (
            prompt_path
        )

    def load(
        self,
        prompt_name: str,
        version: str,
    ) -> dict[str, str]:

        if not self.prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: "
                f"{self.prompt_path}"
            )

        with self.prompt_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            prompts = json.load(
                file
            )

        try:
            return (
                prompts[
                    prompt_name
                ][
                    version
                ]
            )

        except KeyError as exc:
            raise KeyError(
                "Prompt not found: "
                f"{prompt_name}:{version}"
            ) from exc


class RiskGenerator:
    """
    Phase 2 - Step 2: Risk Generation

    Input:
        risk_candidates.json

    Responsibilities:
    - Read deterministic risk candidates
    - Group candidates into bounded generation contexts
    - Ask the LLM ONLY for:
        * concise title
        * grounded 2-3 sentence description
        * canonical category
    - Ensure every candidate is returned exactly once
    - Apply hybrid category resolution using source taxonomy, LLM classification, and deterministic fallback
    - Attach source section/page/block/mitigation deterministically

    The LLM no longer discovers whether something is a risk.
    """

    def __init__(
        self,
        *,
        input_path: Path,
        prompt_path: Path,
        prompt_name: str,
        prompt_version: str,
        logger,
    ):
        self.input_path = (
            input_path
        )

        self.prompt_path = (
            prompt_path
        )

        self.prompt_name = (
            prompt_name
        )

        self.prompt_version = (
            prompt_version
        )

        self.logger = logger

        self.prompt_store = (
            PromptStore(
                prompt_path
            )
        )

        self.llm_client = (
            OpenRouterClient(
                logger=logger
            )
        )

        self.semantic_retries = int(
            os.getenv(
                "GENERATION_SEMANTIC_RETRIES",
                "1",
            )
        )

    # ------------------------------------------------------------------
    # INPUT
    # ------------------------------------------------------------------

    def load_candidates(
        self,
    ) -> dict[str, Any]:

        self.logger.info(
            "STEP_2 | candidate_load | STARTED | file=%s",
            self.input_path,
        )

        if not self.input_path.exists():
            raise FileNotFoundError(
                f"Candidate file not found: {self.input_path}"
            )

        with self.input_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        count = len(
            data.get(
                "candidate_analysis",
                {},
            ).get(
                "candidates",
                [],
            )
        )

        self.logger.info(
            "STEP_2 | candidate_load | SUCCESS | candidates=%s",
            count,
        )

        return data

    # ------------------------------------------------------------------
    # PROMPTS
    # ------------------------------------------------------------------

    def _load_prompt(
        self,
    ) -> dict[str, str]:

        prompt = (
            self.prompt_store.load(
                self.prompt_name,
                self.prompt_version,
            )
        )

        prompt_hash = (
            hashlib.sha256(
                (
                    prompt[
                        "system_prompt"
                    ]
                    + prompt[
                        "user_prompt_template"
                    ]
                ).encode(
                    "utf-8"
                )
            )
            .hexdigest()[:12]
        )

        self.logger.info(
            "STEP_2 | prompt_load | "
            "name=%s | version=%s | hash=%s",
            self.prompt_name,
            self.prompt_version,
            prompt_hash,
        )

        return prompt

    # ------------------------------------------------------------------
    # CONTEXT
    # ------------------------------------------------------------------

    @staticmethod
    def _group_candidates(
        candidates: list[
            dict[str, Any]
        ],
    ) -> list[
        dict[str, Any]
    ]:
        """
        Group by source + topic.

        This keeps prompts small while allowing multiple explicit
        candidates from one topic (for example G1) to be generated
        together.
        """

        groups: dict[
            tuple[str, str, str],
            list[dict[str, Any]],
        ] = defaultdict(list)

        for candidate in candidates:

            key = (
                candidate.get(
                    "source_type",
                    "",
                ),
                candidate.get(
                    "section",
                    "",
                ),
                candidate.get(
                    "topic",
                    "",
                ),
            )

            groups[key].append(
                candidate
            )

        contexts = []

        for (
            source_type,
            section,
            topic,
        ), items in groups.items():

            contexts.append(
                {
                    "source_type": (
                        source_type
                    ),
                    "section": (
                        section
                    ),
                    "topic": (
                        topic
                    ),
                    "candidates": (
                        items
                    ),
                }
            )

        return contexts

    @staticmethod
    def _candidate_prompt_payload(
        candidates: list[
            dict[str, Any]
        ],
    ) -> str:
        """
        Only send content required for semantic generation.

        Page/block/section remain outside the generation contract.
        """

        payload = []

        for candidate in candidates:

            payload.append(
                {
                    "candidate_id": (
                        candidate[
                            "candidate_id"
                        ]
                    ),
                    "candidate_type": (
                        candidate.get(
                            "candidate_type"
                        )
                    ),
                    "source_title": (
                        candidate.get(
                            "source_title"
                        )
                    ),
                    "candidate_text": (
                        candidate.get(
                            "candidate_text"
                        )
                    ),
                    "potential_impact": (
                        candidate.get(
                            "potential_impact"
                        )
                    ),
                    "sub_topic": (
                        candidate.get(
                            "sub_topic"
                        )
                    ),
                    "materiality_type": (
                        candidate.get(
                            "materiality_type"
                        )
                    ),
                    "value_chain": (
                        candidate.get(
                            "value_chain"
                        )
                    ),
                }
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )

    # ------------------------------------------------------------------
    # GENERATION SCHEMA
    # ------------------------------------------------------------------

    @staticmethod
    def _generation_schema(
    ) -> dict[str, Any]:

        return {
            "type": "object",
            "properties": {
                "risks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate_id": {
                                "type": "string"
                            },
                            "title": {
                                "type": "string"
                            },
                            "description": {
                                "type": "string"
                            },
                            "category": {
                                "type": "string",
                                "enum": [
                                    "financial",
                                    "operational",
                                    "regulatory",
                                    "market",
                                    "climate",
                                    "cyber",
                                    "supply_chain",
                                    "governance",
                                    "workforce",
                                    "geopolitical",
                                    "other",
                                ],
                            },
                        },
                        "required": [
                            "candidate_id",
                            "title",
                            "description",
                            "category",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": [
                "risks"
            ],
            "additionalProperties": False,
        }

    # ------------------------------------------------------------------
    # SEMANTIC QUALITY CHECK
    # ------------------------------------------------------------------

    @staticmethod
    def _sentence_count(
        text: str,
    ) -> int:

        if not text:
            return 0

        parts = re.split(
            r"(?<=[.!?])\s+",
            text.strip(),
        )

        return len(
            [
                part
                for part in parts
                if part.strip()
            ]
        )

    def _validate_generation_contract(
        self,
        *,
        generated: GeneratedRiskBatch,
        candidates: list[
            dict[str, Any]
        ],
    ) -> tuple[
        bool,
        list[str],
    ]:

        errors = []

        expected_ids = {
            candidate[
                "candidate_id"
            ]
            for candidate in candidates
        }

        generated_ids = [
            risk.candidate_id
            for risk in generated.risks
        ]

        generated_id_set = set(
            generated_ids
        )

        missing = (
            expected_ids
            - generated_id_set
        )

        unexpected = (
            generated_id_set
            - expected_ids
        )

        if missing:
            errors.append(
                f"missing_candidate_ids={sorted(missing)}"
            )

        if unexpected:
            errors.append(
                f"unexpected_candidate_ids={sorted(unexpected)}"
            )

        if (
            len(generated_ids)
            != len(generated_id_set)
        ):
            errors.append(
                "duplicate_candidate_ids"
            )

        for risk in generated.risks:

            sentence_count = (
                self._sentence_count(
                    risk.description
                )
            )

            if not (
                2
                <= sentence_count
                <= 3
            ):
                errors.append(
                    f"{risk.candidate_id}:"
                    f"description_sentences="
                    f"{sentence_count}"
                )

        return (
            not errors,
            errors,
        )

    # ------------------------------------------------------------------
    # CATEGORY RESOLUTION
    # ------------------------------------------------------------------

    def _apply_category_resolution(
        self,
        raw_response: dict[str, Any],
        candidate_map: dict[str, dict[str, Any]],
    ) -> None:
        """
        Resolve risk categories using a hybrid strategy.

        Priority:
        1. Strong deterministic source-topic taxonomy.
        2. Valid category returned by the LLM.
        3. Deterministic title/context fallback.
        """

        risks = raw_response.get("risks", [])

        if not isinstance(risks, list):
            return

        for item in risks:
            if not isinstance(item, dict):
                continue

            candidate_id = item.get("candidate_id")
            candidate = candidate_map.get(candidate_id, {})
            topic = candidate.get("topic")

            # ------------------------------------------------------
            # 1. Strong source-topic taxonomy
            # ------------------------------------------------------

            topic_category = CategoryResolver.resolve_from_topic(topic)

            if topic_category:
                previous_category = item.get("category")
                item["category"] = topic_category

                self.logger.info(
                    "STEP_2 | category_resolution | "
                    "source=topic_taxonomy | "
                    "candidate=%s | "
                    "topic=%s | "
                    "previous=%s | "
                    "resolved=%s",
                    candidate_id,
                    topic,
                    previous_category,
                    topic_category,
                )
                continue

            # ------------------------------------------------------
            # 2. Keep valid LLM category
            # ------------------------------------------------------

            category = item.get("category")

            if category:
                self.logger.info(
                    "STEP_2 | category_resolution | "
                    "source=llm | "
                    "candidate=%s | "
                    "category=%s",
                    candidate_id,
                    category,
                )
                continue

            # ------------------------------------------------------
            # 3. Deterministic fallback
            # ------------------------------------------------------

            resolved = CategoryResolver.resolve(
                {
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                },
                topic=topic,
            )

            item["category"] = resolved

            self.logger.warning(
                "STEP_2 | category_resolution | "
                "source=fallback | "
                "candidate=%s | "
                "category=%s",
                candidate_id,
                resolved,
            )

    # ------------------------------------------------------------------
    # ONE CONTEXT
    # ------------------------------------------------------------------

    def _generate_context(
        self,
        *,
        context: dict[str, Any],
        prompt: dict[str, str],
    ) -> dict[str, Any]:

        candidates = context["candidates"]

        candidate_map = {
            candidate["candidate_id"]: candidate
            for candidate in candidates
        }

        candidate_payload = self._candidate_prompt_payload(candidates)

        base_user_prompt = prompt["user_prompt_template"].format(
            source_type=context["source_type"],
            section=context["section"],
            topic=context["topic"] or "N/A",
            candidate_count=len(candidates),
            candidates=candidate_payload,
        )

        last_errors: list[str] = []

        for attempt in range(self.semantic_retries + 1):

            if attempt == 0:
                user_prompt = base_user_prompt
            else:
                user_prompt = (
                    base_user_prompt
                    + "\n\n"
                    + "PREVIOUS OUTPUT FAILED THESE "
                    + "DETERMINISTIC CHECKS:\n"
                    + "\n".join(last_errors)
                    + "\nCorrect all of them. "
                    + "Return every candidate exactly once."
                )

            raw_response = self.llm_client.generate_structured(
                system_prompt=prompt["system_prompt"],
                user_prompt=user_prompt,
                response_schema=self._generation_schema(),
                schema_name="risk_generation",
            )

            # Resolve categories before Pydantic validation.
            self._apply_category_resolution(
                raw_response,
                candidate_map,
            )

            generated_batch = GeneratedRiskBatch.model_validate(
                raw_response
            )

            valid, errors = self._validate_generation_contract(
                generated=generated_batch,
                candidates=candidates,
            )

            if valid:
                break

            last_errors = errors

            self.logger.warning(
                "STEP_2 | semantic_validation | "
                "FAILED | topic=%s | attempt=%s | errors=%s",
                context.get("topic"),
                attempt + 1,
                errors,
            )

        else:
            raise ValueError(
                "LLM generation failed deterministic "
                f"semantic checks: {last_errors}"
            )

        # ----------------------------------------------------------
        # Deterministically attach source metadata.
        # ----------------------------------------------------------

        final_risks = []

        for generated_risk in generated_batch.risks:
            candidate = candidate_map[
                generated_risk.candidate_id
            ]

            # Enterprise titles are explicit source headers.
            # Never allow the LLM to rename them.
            if candidate.get("source_title"):
                title = candidate["source_title"]
            else:
                title = generated_risk.title

            final_risks.append(
                {
                    "title": title,
                    "description": generated_risk.description,
                    "category": generated_risk.category.value,
                    "section": candidate["section"],
                    "page": candidate["page"],
                    "mitigation": candidate.get(
                        "mitigation_source"
                    ),
                    "source_block_ids": (
                        [candidate["block_id"]]
                        if candidate.get("block_id")
                        else []
                    ),
                }
            )

        self.logger.info(
            "STEP_2 | semantic_validation | "
            "SUCCESS | topic=%s | candidates=%s",
            context.get("topic"),
            len(candidates),
        )

        return {
            "source_type": context["source_type"],
            "section": context["section"],
            "topic": context.get("topic"),
            "source_pages": sorted(
                {
                    candidate["page"]
                    for candidate in candidates
                    if candidate.get("page")
                }
            ),
            "risks": final_risks,
        }

    # ------------------------------------------------------------------
    # MAIN
    # ------------------------------------------------------------------

    def generate(
        self,
    ) -> dict[str, Any]:

        self.logger.info(
            "STEP_2 | generation | STARTED"
        )

        data = (
            self.load_candidates()
        )

        if not (
            self.llm_client
            .health_check()
        ):
            raise RuntimeError(
                "OpenRouter health check failed."
            )

        prompt = (
            self._load_prompt()
        )

        candidates = (
            data.get(
                "candidate_analysis",
                {},
            ).get(
                "candidates",
                [],
            )
        )

        contexts = (
            self._group_candidates(
                candidates
            )
        )

        self.logger.info(
            "STEP_2 | contexts | count=%s | candidates=%s",
            len(contexts),
            len(candidates),
        )

        results = []

        for index, context in enumerate(
            contexts,
            start=1,
        ):

            self.logger.info(
                "STEP_2 | context_generation | "
                "STARTED | %s/%s | topic=%s | candidates=%s",
                index,
                len(contexts),
                context.get(
                    "topic"
                ),
                len(
                    context[
                        "candidates"
                    ]
                ),
            )

            result = (
                self._generate_context(
                    context=context,
                    prompt=prompt,
                )
            )

            results.append(
                result
            )

            self.logger.info(
                "STEP_2 | context_generation | "
                "SUCCESS | topic=%s | risks=%s",
                context.get(
                    "topic"
                ),
                len(
                    result[
                        "risks"
                    ]
                ),
            )

        total_risks = sum(
            len(
                context[
                    "risks"
                ]
            )
            for context in results
        )

        output = {
            "document": data.get(
                "document",
                {},
            ),
            "generation": {
                "provider": (
                    "openrouter"
                ),
                "requested_model": (
                    self.llm_client.model
                ),
                "prompt_name": (
                    self.prompt_name
                ),
                "prompt_version": (
                    self.prompt_version
                ),
                "candidate_count": (
                    len(candidates)
                ),
                "generated_risk_count": (
                    total_risks
                ),
                "contexts": results,
            },
        }

        self.logger.info(
            "STEP_2 | generation | SUCCESS | risks=%s",
            total_risks,
        )

        return output

    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------

    def save(
        self,
        data: dict[str, Any],
        output_path: Path,
    ) -> None:

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
            )

        self.logger.info(
            "STEP_2 | output_write | SUCCESS | output=%s",
            output_path,
        )