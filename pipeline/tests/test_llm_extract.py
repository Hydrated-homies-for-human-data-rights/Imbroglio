"""Extraction with a fake Anthropic client: no network, no cost, deterministic."""

import json
from types import SimpleNamespace

from imbroglio import llm_extract
from imbroglio.rubric import load

RUBRIC = load("v0")
DOC = ("Privacy Policy. We do not sell your personal information. "
       "We share information with advertising partners to show you relevant ads. "
       "We retain your data for as long as necessary.")


class FakeClient:
    def __init__(self, payload=None, stop_reason="end_turn", model="claude-haiku-4-5"):
        self.calls = []
        text = json.dumps(payload) if payload is not None else ""
        self.response = SimpleNamespace(
            model=model, stop_reason=stop_reason,
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0),
        )
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _payload(*items):
    return {"findings": [dict(check_id=c, status=s, quotes=q, explanation="e") for c, s, q in items]}


def test_verified_unverified_and_unanswered():
    payload = _payload(
        ("sells_personal_data", "no", ["We do not sell your personal information."]),
        ("shares_for_advertising", "yes", ["We sell data to anyone who asks."]),   # fabricated quote
        ("retention_period", "vague", ["We retain your data for as long as necessary."]),
        ("security_measures", "not_disclosed", []),
    )
    r = llm_extract.extract(DOC, RUBRIC, "haiku", client=FakeClient(payload))
    by = {f.check_id: f for f in r.findings}
    assert r.status == "ok" and len(r.findings) == len(RUBRIC.checks)
    assert by["sells_personal_data"].verified
    assert not by["shares_for_advertising"].verified           # quote not in document
    assert by["retention_period"].verified
    assert by["security_measures"].verified and by["security_measures"].quotes == []
    assert by["breach_notification"].status == llm_extract.UNANSWERED
    assert not by["breach_notification"].verified
    assert r.quote_verification_rate == 2 / 3


def test_status_outside_rubric_is_rejected():
    payload = _payload(("sells_personal_data", "probably", ["We do not sell your personal information."]))
    by = {f.check_id: f for f in llm_extract.extract(DOC, RUBRIC, "haiku", client=FakeClient(payload)).findings}
    assert not by["sells_personal_data"].verified
    assert "not an allowed status" in by["sells_personal_data"].explanation


def test_not_disclosed_with_quotes_is_contradictory():
    payload = _payload(("sells_personal_data", "not_disclosed", ["We do not sell your personal information."]))
    by = {f.check_id: f for f in llm_extract.extract(DOC, RUBRIC, "haiku", client=FakeClient(payload)).findings}
    assert not by["sells_personal_data"].verified


def test_refusal_and_cutoff_are_recorded_not_raised():
    assert llm_extract.extract(DOC, RUBRIC, "haiku", client=FakeClient(stop_reason="refusal")).status == "refused"
    r = llm_extract.extract(DOC, RUBRIC, "haiku", client=FakeClient(stop_reason="max_tokens"))
    assert r.status == "error" and "max_tokens" in r.error


def test_request_settings_per_model():
    c = FakeClient(_payload())
    llm_extract.extract(DOC, RUBRIC, "haiku", client=c)
    assert c.calls[-1]["extra_body"] == {"temperature": 0}
    assert c.calls[-1]["output_config"]["format"]["type"] == "json_schema"
    llm_extract.extract(DOC, RUBRIC, "opus", client=c)
    call = c.calls[-1]
    assert call["model"] == "claude-opus-5"
    assert call["output_config"]["effort"] == "medium"
    assert "temperature" not in call.get("extra_body", {})        # rejected by Opus 5
    assert call["extra_body"]["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]


def test_cost_uses_the_model_that_answered():
    r = llm_extract.extract(DOC, RUBRIC, "opus", client=FakeClient(_payload(), model="claude-sonnet-5"))
    assert r.model == "claude-sonnet-5"
    assert abs(r.cost_usd - (1000 * 2.0 + 200 * 10.0) / 1e6) < 1e-12


def test_system_prompt_is_static_and_lists_every_check():
    a, b = llm_extract.system_prompt(RUBRIC), llm_extract.system_prompt(RUBRIC)
    assert a == b                                             # cacheable: no timestamps or ids
    assert all(c.id in a for c in RUBRIC.checks)


def test_overlong_document_is_refused_not_truncated():
    r = llm_extract.extract("x" * (llm_extract.MAX_DOCUMENT_CHARS + 1), RUBRIC, "haiku",
                            client=FakeClient(_payload()))
    assert r.status == "error" and "too long" in r.error
