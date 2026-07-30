from __future__ import annotations

import json

from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_worker.r803_evaluation_provider import ProviderResult


class DeterministicProvider:
    provider = "openai"
    model = "gpt-5.5"

    def generate(self, messages, *, node_key: str) -> ProviderResult:
        if node_key == "quick":
            payload = self._quick(str(messages[-1]["content"]))
        else:
            variables = json.loads(str(messages[-1]["content"]))
            payload = getattr(self, f"_{node_key}")(variables)
        return ProviderResult(
            output=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            input_tokens=10,
            output_tokens=5,
            usage_final=True,
        )

    @staticmethod
    def _quick(content: str) -> dict[str, object]:
        question = content.split("Question:\n", 1)[1].split("\n\nAsset evidence context:", 1)[0]
        cases = {
            "Compare the change described by the PDF chart with the image observation.": {
                "answer": "The PDF trend rises after the third point, while the image says Release 4 begins the sustained drop.",
                "claims": [
                    {
                        "text": "The PDF trend rises after the third point.",
                        "evidenceIds": ["answer-pdf-chart"],
                    },
                    {
                        "text": "The image says Release 4 begins the sustained drop.",
                        "evidenceIds": ["answer-image-trend"],
                    },
                ],
                "conflictDetected": True,
            },
            "Summarize the Atlas score and the image's verification constraint.": {
                "answer": "Atlas has a score of 91.4. Verify the chart and caption together.",
                "claims": [
                    {"text": "Atlas has a score of 91.4.", "evidenceIds": ["answer-pdf-table"]},
                    {
                        "text": "Verify the chart and caption together.",
                        "evidenceIds": ["answer-image-constraint"],
                    },
                ],
                "conflictDetected": False,
            },
            "Are the PDF trend and the image observation directionally consistent? Explain the conflict.": {
                "answer": "They conflict: the PDF trend rises, while the image observation falls in a sustained drop.",
                "claims": [
                    {
                        "text": "The PDF trend rises after the third point.",
                        "evidenceIds": ["answer-pdf-chart"],
                    },
                    {
                        "text": "The image observation falls in a sustained drop.",
                        "evidenceIds": ["answer-image-trend"],
                    },
                ],
                "conflictDetected": True,
            },
            "What evidence must be checked together before accepting the image observation?": {
                "answer": "Verify the chart and caption together.",
                "claims": [
                    {
                        "text": "Verify the chart and caption together.",
                        "evidenceIds": ["answer-image-constraint"],
                    }
                ],
                "conflictDetected": False,
            },
            "What energy consumption does the PDF report for Atlas?": {
                "answer": "The selected assets do not contain supporting evidence for Atlas energy consumption.",
                "claims": [],
                "conflictDetected": False,
            },
            "Which production customer approved the release shown in these fixtures?": {
                "answer": "The selected assets do not contain supporting evidence identifying a production customer.",
                "claims": [],
                "conflictDetected": False,
            },
        }
        return cases[question]

    @staticmethod
    def _planner(variables: dict[str, object]) -> dict[str, object]:
        scope = variables["frozenAssetScope"]
        assert isinstance(scope, dict)
        assets = scope["assets"]
        assert isinstance(assets, list)
        return {
            "summary": "Evaluate the frozen evidence scope.",
            "knownGaps": [],
            "estimatedProviderCalls": 5,
            "subproblems": [
                {
                    "question": variables["question"],
                    "assetIds": [item["assetId"] for item in assets],
                    "expectedEvidence": [],
                }
            ],
        }

    @staticmethod
    def _researcher(variables: dict[str, object]) -> dict[str, object]:
        subproblem = variables["subproblem"]
        tools = variables["toolContracts"]
        assert isinstance(subproblem, dict) and isinstance(tools, dict)
        question = str(subproblem["question"]).casefold()
        evidence = tools["evidence"]
        assert isinstance(evidence, list)
        claims: list[dict[str, object]] = []
        for item in evidence:
            content = str(item["content"])
            lowered = content.casefold()
            selected = False
            if "energy consumption" in question or "production customer" in question:
                selected = False
            elif "compare the change" in question or "directionally consistent" in question:
                selected = "trend rises" in lowered or "latency falls" in lowered
            elif "atlas score" in question:
                selected = "atlas" in lowered or "verify chart" in lowered
            elif "checked together" in question:
                selected = "verify chart" in lowered
            if selected:
                claims.append(
                    {
                        "text": f"{item['assetId']}: {content}",
                        "evidenceHandleIds": [item["evidenceHandle"]],
                    }
                )
        return {"claims": claims}

    @staticmethod
    def _verifier(variables: dict[str, object]) -> dict[str, object]:
        claims = variables["claims"]
        assert isinstance(claims, list)
        return {"claims": [{"id": item["id"], "status": "supported"} for item in claims]}

    @staticmethod
    def _critic(variables: dict[str, object]) -> dict[str, object]:
        claims = variables["claims"]
        assert isinstance(claims, list)
        combined = " ".join(str(item["text"]) for item in claims).casefold()
        conflict_ids = (
            [item["id"] for item in claims]
            if "trend rises" in combined and "latency falls" in combined
            else []
        )
        return {"conflictClaimIds": conflict_ids}

    @staticmethod
    def _synthesizer(variables: dict[str, object]) -> dict[str, object]:
        claims = variables["claims"]
        assert isinstance(claims, list)
        return {
            "factClaimIds": [item["id"] for item in claims if item["conflictStatus"] == "none"],
            "unresolvedClaimIds": [
                item["id"] for item in claims if item["conflictStatus"] == "resolved_unresolved"
            ],
        }


class CampaignProvider(DeterministicProvider):
    def __init__(self, *, fail_mode: str | None = None, fail_round_trigger: int = 1) -> None:
        self.fail_mode = fail_mode
        self.fail_round_trigger = fail_round_trigger
        self.round_hits = 0
        self.calls = 0

    def generate(self, messages, *, node_key: str) -> ProviderResult:
        self.calls += 1
        if node_key == "quick":
            self.round_hits += 1
        if (
            self.fail_mode == "schema"
            and node_key == "researcher"
            and self.round_hits >= self.fail_round_trigger
        ):
            return ProviderResult('{"claims":[{"text":"x"}]}', 3, 2, True)
        if self.fail_mode == "outage":
            raise ModelProviderError("generation_provider_unreachable", "Provider unavailable.")
        return super().generate(messages, node_key=node_key)
