"""The report as a document somebody keeps: complete, self-contained and reproducible.

A passport that only reads correctly while the server is up is a dashboard link, not a
passport. These tests treat the downloaded file as the artefact: everything it claims must
be in it, nothing it needs may live on a network, and two downloads must be the same
bytes.
"""
from __future__ import annotations

import json
import re

import pytest

POSITIVE = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}
NO_DATA = {"aoi_id": "RU_MORDOVIA_04", "year_start": 2019, "year_end": 2024}
CLAIMED = {**POSITIVE, "claimed_units": 100000}

# Everything the report has to carry, and where a reader would look for it.
REQUIRED_SECTIONS = (
    "Запрос", "Запас и изменение", "От изменения к единицам", "Базовая линия",
    "Неопределённость", "Покрытие и качество", "Сценарная стоимость", "Источники",
    "Риски", "Методика", "Ограничения", "Идентичность",
)


def _analysed(harness, body=POSITIVE, key="report-key-000001"):
    job = harness.analyse(body, key=key)
    assert job["job_state"] == "SUCCEEDED", job
    return job


def _html(harness, analysis_id: str) -> str:
    response = harness.client.get(
        f"/api/v2/analyses/{analysis_id}/report?format=html",
        headers=harness.api.headers())
    assert response.status_code == 200
    return response.text


# -- completeness --------------------------------------------------------------------------
def test_the_html_report_carries_every_required_section(harness):
    html = _html(harness, _analysed(harness, CLAIMED, "sections-key-00001")["analysis_id"])
    for section in REQUIRED_SECTIONS:
        assert f">{section}" in html or section in html, section
    assert "Заявление" in html, "a stated volume must appear in the report"
    # Zones appear when there are zones; an empty table would be a worse answer than none.
    has_zones = bool(_analysed(harness, CLAIMED, "sections-key-00002")["result"]["zones"])
    assert ("Зоны изменения" in html) is has_zones


def test_the_html_report_states_the_plot_the_period_and_the_area(harness):
    job = _analysed(harness, POSITIVE, "plot-key-00000001")
    html = _html(harness, job["analysis_id"])
    areas = job["result"]["areas"]
    assert "RU_TVER_01" in html
    assert "2019" in html and "2024" in html
    assert f"{areas['requested_ha']:,.4f}".replace(",", " ") in html


def test_the_html_report_states_q_and_the_buffer(harness):
    job = _analysed(harness, POSITIVE, "buffer-key-00001")
    html = _html(harness, job["analysis_id"])
    units = job["result"]["units"]
    assert str(units["q"]) in html
    assert "Буфер" in html
    assert f"{units['buffer_tco2e']:,.3f}".replace(",", " ") in html


def test_the_html_report_states_the_baseline_and_the_interval(harness):
    job = _analysed(harness, POSITIVE, "baseint-key-00001")
    html = _html(harness, job["analysis_id"])
    result = job["result"]
    assert result["baseline"]["baseline_id"] in html
    assert "сценарный интервал" in html
    assert "не эмпирически калиброванный" in html or "не эмпирически" in html


def test_the_html_report_states_the_method_and_its_versions(harness):
    job = _analysed(harness, POSITIVE, "method-key-000001")
    html = _html(harness, job["analysis_id"])
    identity = job["result"]["identity"]
    assert identity["method_version"] in html
    assert identity["schema_version"] in html
    assert identity["dataset_version"] in html


def test_the_html_report_states_the_projection_and_keeps_it_apart_from_facts(harness):
    job = _analysed(harness, POSITIVE, "projrep-key-00001")
    html = _html(harness, job["analysis_id"])
    assert "2029" in html
    assert "PROJECTION" in html and "FACT" in html
    assert "не прогноз состояния участка" in html


def test_the_html_report_states_every_hash_and_the_identifier(harness):
    job = _analysed(harness, POSITIVE, "hashes-key-000001")
    html = _html(harness, job["analysis_id"])
    result = job["result"]
    for value in (result["identity"]["analysis_id"], result["identity"]["geometry_hash"],
                  result["identity"]["input_hash"], result["identity"]["dataset_hash"],
                  result["passport"]["content_hash"], result["passport"]["report_hash"]):
        assert value in html, value
    assert result["passport"]["created_at"] in html


def test_the_json_report_is_the_whole_result(harness):
    job = _analysed(harness, CLAIMED, "jsonall-key-00001")
    document = harness.api.get(f"/analyses/{job['analysis_id']}/report", "Report")
    for block in ("areas", "change", "baseline", "uncertainty", "units", "claim",
                  "risks", "projection", "scenario_values", "sources", "zones",
                  "limitations", "identity", "passport", "evidence"):
        assert block in document["result"], block
    assert document["result"] == job["result"]


# -- self-contained ------------------------------------------------------------------------
def test_the_html_report_loads_nothing_from_a_network(harness):
    """A document that needs a host to render is not a document you can keep."""
    html = _html(harness, _analysed(harness, POSITIVE, "offline-key-00001")["analysis_id"])
    lowered = html.lower()
    assert "<script" not in lowered and "</script" not in lowered
    assert "<link" not in lowered and "<iframe" not in lowered
    assert "@import" not in lowered
    for scheme in ("http://", "https://", "//cdn", "data:text/html"):
        assert scheme not in lowered, scheme
    # No handler that could fetch something later either.
    assert not re.search(r"\son[a-z]+\s*=", lowered)


def test_the_html_report_leaks_no_secret_and_no_local_path(harness):
    from backend.app.config import REPO_ROOT

    from .conftest import PASSWORD, SESSION

    job = _analysed(harness, POSITIVE, "leak-key-00000001")
    html = _html(harness, job["analysis_id"])
    for secret in (PASSWORD, SESSION, harness.api.tokens["VERIFIER"]):
        assert secret not in html
    for path in (str(REPO_ROOT), str(harness.tmp_path), "/Users/", "C:\\\\"):
        assert path not in html, path
    assert "Authorization" not in html and "Bearer" not in html
    assert "Traceback" not in html and ".py" not in html


def test_the_report_carries_no_stack_trace_even_when_nothing_was_computed(harness):
    job = _analysed(harness, NO_DATA, "leaknull-key-0001")
    html = _html(harness, job["analysis_id"])
    assert "Traceback" not in html and "Exception" not in html
    assert "не рассчитаны" in html


# -- reproducible --------------------------------------------------------------------------
def test_two_downloads_are_the_same_bytes(harness):
    job = _analysed(harness, POSITIVE, "bytes-key-0000001")
    path = f"/api/v2/analyses/{job['analysis_id']}/report?format=html"
    first = harness.client.get(path, headers=harness.api.headers()).content
    second = harness.client.get(path, headers=harness.api.headers()).content
    assert first == second


def test_the_same_request_on_a_fresh_deployment_produces_the_same_report_hash(harness,
                                                                              tmp_path):
    from .conftest import Harness

    first = _analysed(harness, POSITIVE, "fresh-key-00000001")
    other = Harness(tmp_path / "second")
    second = other.analyse(POSITIVE, key="fresh-key-00000002")
    assert second["job_state"] == "SUCCEEDED"
    assert second["result"]["passport"]["report_hash"] == \
        first["result"]["passport"]["report_hash"]
    assert second["result"]["passport"]["content_hash"] == \
        first["result"]["passport"]["content_hash"]


def test_the_report_hash_does_not_depend_on_when_it_was_rendered(harness):
    """The hash identifies the content, not the rendering or the download."""
    job = _analysed(harness, POSITIVE, "whenhash-key-0001")
    document = harness.api.get(f"/analyses/{job['analysis_id']}/report", "Report")
    assert document["generated_at"] == job["result"]["run"]["created_at"]
    assert document["report_hash"] == job["result"]["passport"]["report_hash"]
    # Downloading again does not restamp it.
    again = harness.api.get(f"/analyses/{job['analysis_id']}/report", "Report")
    assert again["generated_at"] == document["generated_at"]


def test_the_report_hash_covers_the_content_and_not_the_passport_status(harness):
    """Finalizing must not invalidate a report somebody already downloaded."""
    from backend.app.v2.assemble import content_view
    from backend.app.v2.contracts import digest
    from backend.app.v2.report import REPORT_SCHEMA_VERSION

    job = _analysed(harness, POSITIVE, "cover-key-0000001")
    result = job["result"]
    recomputed = digest({"report": REPORT_SCHEMA_VERSION, "content": content_view(result)})
    assert recomputed == result["passport"]["report_hash"]
    assert "passport" not in content_view(result)


# -- a tampered file ------------------------------------------------------------------------
def test_a_tampered_report_no_longer_matches_its_hash(harness):
    from backend.app.v2.assemble import content_view
    from backend.app.v2.contracts import digest
    from backend.app.v2.report import REPORT_SCHEMA_VERSION

    job = _analysed(harness, POSITIVE, "tamper-key-000001")
    document = harness.api.get(f"/analyses/{job['analysis_id']}/report", "Report")

    forged = json.loads(json.dumps(document))
    forged["result"]["units"]["q"] = 999999
    recomputed = digest({"report": REPORT_SCHEMA_VERSION,
                         "content": content_view(forged["result"])})
    assert recomputed != document["report_hash"], \
        "a changed number must not keep the hash it was published with"


def test_a_stored_report_cannot_be_rewritten_in_place(harness):
    import sqlite3

    job = _analysed(harness, POSITIVE, "immut-key-0000001")
    with pytest.raises(sqlite3.IntegrityError):
        with harness.ctx.db.transaction() as conn:
            conn.execute("UPDATE lens_reports SET html_bytes = ? WHERE analysis_id = ?",
                         (b"<html>forged</html>", job["analysis_id"]))


def test_the_report_footer_says_what_a_hash_does_and_does_not_do(harness):
    html = _html(harness, _analysed(harness, POSITIVE, "footer-key-000001")["analysis_id"])
    assert "не предотвращает" in html
    assert "двойную продажу" in html
    assert "не удостоверяет истинность расчёта" in html
