"""Unpaid service-provider compatibility for frozen historical and v4 role inputs."""

import json

import pytest
from citeframe_research_persistence.conflict_contract import (
    INVESTIGATOR_SCHEMA,
    validate_investigation,
)
from research_service_worker import FixtureGeneration


def generate(value):
    return json.loads(
        FixtureGeneration().generate(
            [{"role": "user", "content": json.dumps(value)}],
            max_output_tokens=1000,
        )
    )


def test_service_provider_handles_nested_investigator_payload():
    claims = [{"id": "claim", "evidenceHandleIds": ["source"]}]
    evidence = [
        {
            "id": "source",
            "excerpt": "Immutable source without a disambiguating version.",
        }
    ]
    value = {
        "investigation": {"claims": claims, "evidence": evidence},
        "resultSchema": INVESTIGATOR_SCHEMA,
    }
    assert "claims" not in value
    result = generate(value)
    validate_investigation(result, claims=claims, evidence=evidence)
    assert result["revisions"] == [] and result["nextQuery"] is None
    assert result["gaps"]
    assert result["inspections"][0]["quote"] == evidence[0]["excerpt"]
    assert all(
        result["inspections"][0][key] is None
        for key in ("version", "environment", "time", "conditions")
    )


@pytest.mark.parametrize("adaptive", [False, True])
def test_service_provider_retains_historical_researcher_shape(adaptive):
    value = {
        "toolContracts": {"evidence": [{"evidenceHandle": "source"}]},
        "resultSchema": {"properties": {"nextQuery": {}}} if adaptive else {},
    }
    expected = {
        "claims": [
            {
                "text": "The source preserves immutable evidence.",
                "evidenceHandleIds": ["source"],
            }
        ]
    }
    if adaptive:
        expected["nextQuery"] = None
    assert generate(value) == expected


@pytest.mark.parametrize(
    "role,extra,expected",
    [
        (
            "verifier",
            {"reasonTaxonomy": {}},
            {"claims": [{"id": "claim", "status": "supported"}]},
        ),
        (
            "critic",
            {"resultSchema": {"properties": {"conflictClaimIds": {}}}},
            {"conflictClaimIds": ["claim"]},
        ),
        ("synthesizer", {}, {"factClaimIds": [], "unresolvedClaimIds": ["claim"]}),
    ],
)
def test_service_provider_retains_historical_selection(role, extra, expected):
    assert generate({"claims": [{"id": "claim"}], **extra}) == expected


def test_service_provider_retains_historical_planner():
    assert generate(
        {"planOutputSchema": {}, "frozenAssetScope": {"assets": [{"assetId": "asset"}]}}
    ) == {
        "summary": "One bounded source question.",
        "subproblems": [
            {
                "question": "What does the source establish?",
                "assetIds": ["asset"],
                "expectedEvidence": [],
            }
        ],
        "knownGaps": [],
        "estimatedProviderCalls": 5,
    }
