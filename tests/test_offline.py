from unittest.mock import MagicMock

import pytest

from dg import Deepgram, DeepgramError, lint_keyterms
from scoring import term_hits, wer


def test_lint_flags_comma_joined_list():
    problems = lint_keyterms(["Gainsight, ChurnZero, Vitally"])
    assert len(problems) == 1
    assert "ONE literal term" in problems[0]
    assert "['Gainsight', 'ChurnZero', 'Vitally']" in problems[0]


def test_lint_flags_legacy_weight_syntax():
    problems = lint_keyterms(["Adaptalytics:2"])
    assert any("not support weights" in p and "'Adaptalytics'" in p for p in problems)


def test_lint_passes_clean_terms_including_phrases():
    assert lint_keyterms(["Dayforce", "customer service", "OAuth"]) == []


def test_lint_flags_generic_words_and_too_many_terms():
    assert any("generic" in p for p in lint_keyterms(["the"]))
    assert any("100-term limit" in p for p in lint_keyterms([f"term{i}" for i in range(101)]))


def test_wer_counts_substitutions_insertions_deletions():
    assert wer("our product is adaptalytics", "our product is adaptalytics") == 0.0
    assert wer("our product is adaptalytics", "our product is adapt a lytics") == pytest.approx(3 / 4)
    assert wer("call twilio now", "call now") == pytest.approx(1 / 3)


def test_term_hits_matches_whole_words_and_caps_at_said():
    ref = "We use Dayforce. Dayforce syncs nightly."
    assert term_hits("Dayforce", ref, "we use day force dayforce syncs nightly") == (1, 2)
    assert term_hits("Zoho", "Zoho and Freshdesk", "zoho zoho and freshdesk") == (1, 1)
    assert term_hits("customer service", "call customer service", "call customer service") == (1, 1)


def _client(*responses):
    session = MagicMock()
    session.post.side_effect = list(responses)
    return Deepgram(api_key="k", session=session), session


def _resp(status, payload=None):
    r = MagicMock(status_code=status, text="err")
    r.json.return_value = payload or {}
    return r


OK = {"results": {"channels": [{"alternatives": [{"transcript": "hi"}]}]}}


def test_listen_sends_each_keyterm_as_its_own_parameter(monkeypatch):
    client, session = _client(_resp(200, OK))
    client.listen(b"audio", ["Gainsight", "customer service"])
    params = session.post.call_args.kwargs["params"]
    assert ("keyterm", "Gainsight") in params
    assert ("keyterm", "customer service") in params
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Token k"


def test_retries_rate_limit_but_not_bad_request(monkeypatch):
    monkeypatch.setattr("dg.time.sleep", lambda s: None)
    client, session = _client(_resp(429), _resp(200, OK))
    client.listen(b"audio")
    assert session.post.call_count == 2

    client, session = _client(_resp(400))
    with pytest.raises(DeepgramError):
        client.listen(b"audio")
    assert session.post.call_count == 1
