from __future__ import annotations

import json
import os
import random
import re
import time
from typing import Any

import httpx
from dotenv import load_dotenv


class OpenRouterClient:
    """
    Reusable OpenRouter client.

    Responsibilities:
    - Load configuration
    - Check OpenRouter connectivity
    - Perform structured generation
    - Enable response healing
    - Parse model JSON defensively
    - Retry temporary API/provider failures
    - Respect Retry-After for rate limits
    - Log model, latency, token usage and failures

    Prompt construction is handled outside this class.
    """

    RETRYABLE_STATUS_CODES = {
        429,
        500,
        502,
        503,
        504,
    }

    def __init__(self, logger):
        load_dotenv()

        self.logger = logger

        self.api_key = os.getenv(
            "OPENROUTER_API_KEY"
        )

        self.model = os.getenv(
            "OPENROUTER_MODEL",
            "google/gemma-4-26b-a4b-it:free",
        )

        self.base_url = os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1",
        ).rstrip("/")

        self.timeout = float(
            os.getenv(
                "OPENROUTER_TIMEOUT",
                "120",
            )
        )

        self.max_retries = int(
            os.getenv(
                "OPENROUTER_MAX_RETRIES",
                "5",
            )
        )

        self.retry_base_seconds = float(
            os.getenv(
                "OPENROUTER_RETRY_BASE_SECONDS",
                "5",
            )
        )

        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not configured."
            )

    # ------------------------------------------------------------------
    # HEADERS
    # ------------------------------------------------------------------

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # HEALTH CHECK
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """
        Verify basic OpenRouter connectivity.

        This does not consume a generation request.
        """
        self.logger.info(
            "STEP_2 | llm_health | STARTED | "
            "provider=openrouter | model=%s",
            self.model,
        )

        url = (
            f"{self.base_url}/models"
        )

        start_time = (
            time.perf_counter()
        )

        try:
            with httpx.Client(
                timeout=self.timeout
            ) as client:

                response = client.get(
                    url,
                    headers=self.headers,
                )

            elapsed_ms = (
                time.perf_counter()
                - start_time
            ) * 1000

            response.raise_for_status()

            self.logger.info(
                "STEP_2 | llm_health | SUCCESS | "
                "status=%s | latency_ms=%.2f",
                response.status_code,
                elapsed_ms,
            )

            return True

        except Exception:
            self.logger.exception(
                "STEP_2 | llm_health | FAILED"
            )

            return False

    # ------------------------------------------------------------------
    # RETRY HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _get_retry_after_from_headers(
        response: httpx.Response,
    ) -> float | None:
        """
        Read HTTP Retry-After header when provided.
        """
        retry_after = response.headers.get(
            "Retry-After"
        )

        if not retry_after:
            return None

        try:
            return float(
                retry_after
            )

        except ValueError:
            return None

    @staticmethod
    def _get_retry_after_from_body(
        response: httpx.Response,
    ) -> float | None:
        """
        OpenRouter/provider errors may contain:

        {
            "error": {
                "metadata": {
                    "retry_after_seconds": 22
                }
            }
        }
        """

        try:
            body = response.json()

        except Exception:
            return None

        try:
            retry_after = (
                body
                .get("error", {})
                .get("metadata", {})
                .get(
                    "retry_after_seconds"
                )
            )

            if retry_after is None:
                return None

            return float(
                retry_after
            )

        except (
            TypeError,
            ValueError,
            AttributeError,
        ):
            return None

    def _calculate_retry_delay(
        self,
        *,
        response: httpx.Response,
        attempt: int,
    ) -> float:
        """
        Retry priority:

        1. Retry-After response header
        2. retry_after_seconds in OpenRouter error metadata
        3. exponential backoff

        Jitter is added to avoid synchronized retries.
        """

        wait_seconds = (
            self._get_retry_after_from_headers(
                response
            )
        )

        if wait_seconds is None:
            wait_seconds = (
                self._get_retry_after_from_body(
                    response
                )
            )

        if wait_seconds is None:
            wait_seconds = (
                self.retry_base_seconds
                * (2 ** attempt)
            )

        jitter = random.uniform(
            0.0,
            1.0,
        )

        return (
            wait_seconds
            + jitter
        )

    def _post_with_retry(
        self,
        *,
        url: str,
        payload: dict[str, Any],
    ) -> httpx.Response:
        """
        Execute an OpenRouter POST request with bounded retries.

        Retries only transient failures:

        - 429 Too Many Requests
        - 500 Internal Server Error
        - 502 Bad Gateway
        - 503 Service Unavailable
        - 504 Gateway Timeout

        Non-retryable errors return immediately.
        """

        with httpx.Client(
            timeout=self.timeout
        ) as client:

            for attempt in range(
                self.max_retries + 1
            ):

                response = client.post(
                    url,
                    headers=self.headers,
                    json=payload,
                )

                status_code = (
                    response.status_code
                )

                # --------------------------------------------------
                # Success or permanent error
                # --------------------------------------------------

                if (
                    status_code
                    not in self.RETRYABLE_STATUS_CODES
                ):
                    return response

                # --------------------------------------------------
                # Retry budget exhausted
                # --------------------------------------------------

                if attempt >= self.max_retries:

                    self.logger.error(
                        "STEP_2 | llm_retry | "
                        "EXHAUSTED | "
                        "status=%s | attempts=%s",
                        status_code,
                        attempt + 1,
                    )

                    return response

                # --------------------------------------------------
                # Calculate delay
                # --------------------------------------------------

                wait_seconds = (
                    self._calculate_retry_delay(
                        response=response,
                        attempt=attempt,
                    )
                )

                self.logger.warning(
                    "STEP_2 | llm_retry | "
                    "status=%s | "
                    "attempt=%s/%s | "
                    "wait_seconds=%.2f",
                    status_code,
                    attempt + 1,
                    self.max_retries,
                    wait_seconds,
                )

                time.sleep(
                    wait_seconds
                )

        raise RuntimeError(
            "Unexpected retry loop termination."
        )

    # ------------------------------------------------------------------
    # JSON CLEANING
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_markdown_fence(
        content: str,
    ) -> str:
        """
        Remove:

            ```json
            {...}
            ```

        or:

            ```
            {...}
            ```
        """

        content = content.strip()

        pattern = re.compile(
            r"^```(?:json)?\s*(.*?)\s*```$",
            flags=(
                re.IGNORECASE
                | re.DOTALL
            ),
        )

        match = pattern.match(
            content
        )

        if match:
            return (
                match
                .group(1)
                .strip()
            )

        return content

    @staticmethod
    def _extract_json_object(
        content: str,
    ) -> str:
        """
        Recover JSON if the model returns explanatory text around it.

        Example:

            Here is the result:
            {...}
        """

        content = content.strip()

        start = content.find("{")
        end = content.rfind("}")

        if start == -1:
            return content

        if end == -1:
            return content

        if end <= start:
            return content

        return content[
            start : end + 1
        ]

    def _parse_json_response(
        self,
        content: Any,
    ) -> dict[str, Any]:
        """
        Parse structured output defensively.

        Recovery order:

        1. Already a dictionary
        2. Direct JSON parsing
        3. Remove markdown fences
        4. Extract outer JSON object
        5. Controlled failure
        """

        if isinstance(
            content,
            dict,
        ):
            return content

        if not isinstance(
            content,
            str,
        ):
            raise TypeError(
                "LLM message content must be "
                "a dictionary or string. "
                f"Received: "
                f"{type(content).__name__}"
            )

        raw_content = content

        # --------------------------------------------------------------
        # Attempt 1: Direct parse
        # --------------------------------------------------------------

        try:
            return json.loads(
                raw_content
            )

        except json.JSONDecodeError as exc:

            self.logger.warning(
                "STEP_2 | json_parse | "
                "DIRECT_FAILED | "
                "line=%s | column=%s | "
                "position=%s",
                exc.lineno,
                exc.colno,
                exc.pos,
            )

        # --------------------------------------------------------------
        # Attempt 2: Remove markdown wrapper
        # --------------------------------------------------------------

        cleaned = (
            self._strip_markdown_fence(
                raw_content
            )
        )

        try:
            parsed = json.loads(
                cleaned
            )

            self.logger.info(
                "STEP_2 | json_parse | "
                "RECOVERED_AFTER_FENCE_REMOVAL"
            )

            return parsed

        except json.JSONDecodeError:
            pass

        # --------------------------------------------------------------
        # Attempt 3: Extract outer JSON
        # --------------------------------------------------------------

        cleaned = (
            self._extract_json_object(
                cleaned
            )
        )

        try:
            parsed = json.loads(
                cleaned
            )

            self.logger.info(
                "STEP_2 | json_parse | "
                "RECOVERED_AFTER_JSON_EXTRACTION"
            )

            return parsed

        except json.JSONDecodeError as exc:

            self.logger.error(
                "STEP_2 | json_parse | FAILED | "
                "line=%s | column=%s | "
                "position=%s",
                exc.lineno,
                exc.colno,
                exc.pos,
            )

            self.logger.error(
                "STEP_2 | malformed_response | "
                "preview=%r",
                raw_content[:3000],
            )

            raise ValueError(
                "LLM returned malformed JSON. "
                "Check the pipeline log for "
                "the response preview."
            ) from exc

    # ------------------------------------------------------------------
    # STRUCTURED GENERATION
    # ------------------------------------------------------------------

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:
        """
        Generate structured JSON through OpenRouter.

        Temporary provider failures are retried automatically.
        """

        url = (
            f"{self.base_url}"
            "/chat/completions"
        )

        payload = {
            "model": self.model,

            "temperature": 0,

            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],

            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_schema,
                },
            },

            # Only use providers/endpoints that support
            # the requested structured-output parameters.
            "provider": {
                "require_parameters": True,
            },

            # Attempt to repair malformed structured JSON.
            "plugins": [
                {
                    "id": "response-healing"
                }
            ],
        }

        self.logger.info(
            "STEP_2 | llm_call | STARTED | "
            "model=%s | schema=%s",
            self.model,
            schema_name,
        )

        start_time = (
            time.perf_counter()
        )

        try:
            # ----------------------------------------------------------
            # Request with transient-failure retries
            # ----------------------------------------------------------

            response = (
                self._post_with_retry(
                    url=url,
                    payload=payload,
                )
            )

            elapsed_ms = (
                time.perf_counter()
                - start_time
            ) * 1000

            # ----------------------------------------------------------
            # Final HTTP failure after retries
            # ----------------------------------------------------------

            if response.status_code >= 400:

                self.logger.error(
                    "STEP_2 | llm_call | FAILED | "
                    "status=%s | response=%s",
                    response.status_code,
                    response.text[:3000],
                )

                response.raise_for_status()

            # ----------------------------------------------------------
            # OpenRouter wrapper response
            # ----------------------------------------------------------

            response_data = (
                response.json()
            )

            model_used = (
                response_data.get(
                    "model",
                    self.model,
                )
            )

            usage = (
                response_data.get(
                    "usage",
                    {},
                )
            )

            self.logger.info(
                "STEP_2 | llm_call | SUCCESS | "
                "requested_model=%s | "
                "resolved_model=%s | "
                "latency_ms=%.2f | "
                "prompt_tokens=%s | "
                "completion_tokens=%s",
                self.model,
                model_used,
                elapsed_ms,
                usage.get(
                    "prompt_tokens"
                ),
                usage.get(
                    "completion_tokens"
                ),
            )

            # ----------------------------------------------------------
            # Extract model choice
            # ----------------------------------------------------------

            choices = (
                response_data.get(
                    "choices",
                    [],
                )
            )

            if not choices:
                raise ValueError(
                    "OpenRouter returned no choices."
                )

            message = (
                choices[0]
                .get(
                    "message",
                    {},
                )
            )

            content = message.get(
                "content"
            )

            if content is None:

                self.logger.error(
                    "STEP_2 | llm_call | "
                    "EMPTY_CONTENT | message=%s",
                    message,
                )

                raise ValueError(
                    "OpenRouter returned no "
                    "message content."
                )

            # ----------------------------------------------------------
            # Parse actual model JSON
            # ----------------------------------------------------------

            return (
                self._parse_json_response(
                    content
                )
            )

        except Exception:

            self.logger.exception(
                "STEP_2 | llm_call | EXCEPTION"
            )

            raise