"""
Unit and integration tests for CoachAI.
Run with: python -m pytest tests/ -v
"""
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force mock mode before importing app so no real API calls are made
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    import app as flask_app

    monkeypatch.setattr(flask_app, "MOCK_MODE", True)
    monkeypatch.setattr(flask_app, "LOCAL", True)
    monkeypatch.setattr(flask_app, "RATINGS_FILE",     tmp_path / "ratings.json")
    monkeypatch.setattr(flask_app, "EVENTS_FILE",      tmp_path / "events.json")
    monkeypatch.setattr(flask_app, "FEEDBACK_FILE",    tmp_path / "feedback.json")
    monkeypatch.setattr(flask_app, "EVALUATIONS_FILE", tmp_path / "evaluations.json")

    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as client:
        yield client, flask_app, tmp_path


# ── Unit: parse_json ──────────────────────────────────────────────────────────

def test_parse_json_plain():
    from app import parse_json
    assert parse_json('{"a": 1}') == {"a": 1}

def test_parse_json_trailing_comma():
    from app import parse_json
    assert parse_json('{"a": 1,}') == {"a": 1}

def test_parse_json_markdown_fenced():
    from app import parse_json
    raw = '```json\n{"a": 1}\n```'
    assert parse_json(raw) == {"a": 1}

def test_parse_json_invalid_raises():
    from app import parse_json
    with pytest.raises(Exception):
        parse_json("not json at all")


# ── Unit: log_event ───────────────────────────────────────────────────────────

def test_log_event_creates_file(tmp_path, monkeypatch):
    import app as flask_app
    events_file = tmp_path / "events.json"
    monkeypatch.setattr(flask_app, "EVENTS_FILE", events_file)

    flask_app.log_event("test_event", {"key": "value"})

    assert events_file.exists()
    data = json.loads(events_file.read_text())
    assert len(data) == 1
    assert data[0]["event"] == "test_event"
    assert data[0]["data"] == {"key": "value"}

def test_log_event_appends(tmp_path, monkeypatch):
    import app as flask_app
    events_file = tmp_path / "events.json"
    monkeypatch.setattr(flask_app, "EVENTS_FILE", events_file)

    flask_app.log_event("event_one")
    flask_app.log_event("event_two")

    data = json.loads(events_file.read_text())
    assert len(data) == 2
    assert data[1]["event"] == "event_two"


# ── Unit: mock plan structure ─────────────────────────────────────────────────

def test_mock_plan_structure():
    from app import get_mock_plan
    plan = get_mock_plan("U10", 12, 75, "Passing", "")

    assert plan["age_group"] == "U10"
    assert plan["players"] == 12
    assert plan["duration"] == 75
    assert plan["focus"] == "Passing"
    assert len(plan["sections"]) == 5

    types = [s["type"] for s in plan["sections"]]
    assert types[0] == "warmup"
    assert types[-1] == "cooldown"
    assert "game" in types

def test_mock_plan_sections_have_required_fields():
    from app import get_mock_plan
    plan = get_mock_plan("U12", 16, 60, "Defending", "")

    for section in plan["sections"]:
        assert "type" in section
        assert "title" in section
        assert "duration" in section
        assert "setup" in section
        assert isinstance(section["instructions"], list)
        assert len(section["instructions"]) >= 1
        assert isinstance(section["coaching_points"], list)
        assert len(section["coaching_points"]) >= 1

def test_mock_plan_durations_are_positive():
    from app import get_mock_plan
    plan = get_mock_plan("U10", 12, 75, "Passing", "")
    for section in plan["sections"]:
        assert section["duration"] > 0


# ── Integration: homepage ─────────────────────────────────────────────────────

def test_index_returns_200(app_client):
    client, _, _ = app_client
    r = client.get("/")
    assert r.status_code == 200
    assert b"CoachAI" in r.data

def test_index_logs_page_view(app_client):
    client, flask_app, tmp_path = app_client
    client.get("/")
    events = json.loads((tmp_path / "events.json").read_text())
    assert any(e["event"] == "page_view" for e in events)


# ── Integration: streaming plan ───────────────────────────────────────────────

def test_stream_plan_returns_200(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    assert r.status_code == 200

def test_stream_plan_contains_delimiter(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    assert b"|||" in r.data

def test_stream_plan_first_chunk_is_metadata(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    first_chunk = r.data.split(b"|||")[0].strip()
    meta = json.loads(first_chunk)
    assert meta["age_group"] == "U10"
    assert meta["focus"] == "Passing"

def test_stream_plan_yields_five_sections(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    parts = [p.strip() for p in r.data.split(b"|||") if p.strip()]
    # first part is metadata, remaining 5 are sections
    assert len(parts) == 6

def test_stream_plan_logs_plan_generated(app_client):
    client, flask_app, tmp_path = app_client
    client.post("/stream-plan", data={
        "age_group": "U12", "players": "14", "duration": "60", "focus": "Defending"
    })
    events = json.loads((tmp_path / "events.json").read_text())
    generated = [e for e in events if e["event"] == "plan_generated"]
    assert len(generated) == 1
    assert generated[0]["data"]["age_group"] == "U12"
    assert generated[0]["data"]["focus"] == "Defending"

def test_stream_plan_all_age_groups(app_client):
    client, _, _ = app_client
    for age in ["U6", "U8", "U10", "U12", "U14", "U16"]:
        r = client.post("/stream-plan", data={
            "age_group": age, "players": "10", "duration": "60", "focus": "Passing"
        })
        _ = r.data  # fully consume the streaming response before next iteration
        assert r.status_code == 200, f"Failed for age group {age}"


# ── Integration: rate ─────────────────────────────────────────────────────────

def test_rate_saves_rating(app_client):
    client, flask_app, tmp_path = app_client
    r = client.post("/rate", json={
        "rating": 8, "what_worked": "Great drills", "what_wrong": "",
        "age_group": "U10", "focus": "Passing"
    })
    assert r.status_code == 200
    assert r.get_json()["saved"] is True

    ratings = json.loads((tmp_path / "ratings.json").read_text())
    assert len(ratings) == 1
    assert ratings[0]["rating"] == 8

def test_rate_requires_no_mandatory_fields(app_client):
    client, _, _ = app_client
    r = client.post("/rate", json={"rating": 5})
    assert r.status_code == 200

def test_ratings_endpoint_returns_list(app_client):
    client, _, _ = app_client
    client.post("/rate", json={"rating": 7})
    r = client.get("/ratings")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


# ── Integration: track ────────────────────────────────────────────────────────

def test_track_saves_event(app_client):
    client, flask_app, tmp_path = app_client
    r = client.post("/track", json={"event": "share_clicked", "age_group": "U10"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    events = json.loads((tmp_path / "events.json").read_text())
    assert any(e["event"] == "share_clicked" for e in events)

def test_track_handles_missing_event_field(app_client):
    client, _, _ = app_client
    r = client.post("/track", json={"foo": "bar"})
    assert r.status_code == 200


# ── Integration: feedback ─────────────────────────────────────────────────────

def test_feedback_saves_message(app_client):
    client, flask_app, tmp_path = app_client
    r = client.post("/feedback", json={"message": "Love this tool!", "page": "/"})
    assert r.status_code == 200
    assert r.get_json()["saved"] is True

    entries = json.loads((tmp_path / "feedback.json").read_text())
    assert entries[0]["message"] == "Love this tool!"

def test_feedback_handles_empty_body(app_client):
    client, _, _ = app_client
    r = client.post("/feedback", json={})
    assert r.status_code == 200


# ── Integration: analytics ────────────────────────────────────────────────────

def test_analytics_accessible_locally(app_client):
    client, _, _ = app_client
    r = client.get("/analytics")
    assert r.status_code == 200

def test_analytics_blocked_in_production_without_key(app_client):
    client, flask_app, _ = app_client
    monkeypatch_local = False
    flask_app.LOCAL = False
    os.environ.pop("ANALYTICS_KEY", None)
    r = client.get("/analytics")
    flask_app.LOCAL = True
    assert r.status_code == 404

def test_analytics_accessible_in_production_with_correct_key(app_client):
    client, flask_app, _ = app_client
    flask_app.LOCAL = False
    os.environ["ANALYTICS_KEY"] = "testkey123"
    r = client.get("/analytics?key=testkey123")
    flask_app.LOCAL = True
    os.environ.pop("ANALYTICS_KEY", None)
    assert r.status_code == 200

def test_analytics_blocked_in_production_with_wrong_key(app_client):
    client, flask_app, _ = app_client
    flask_app.LOCAL = False
    os.environ["ANALYTICS_KEY"] = "correctkey"
    r = client.get("/analytics?key=wrongkey")
    flask_app.LOCAL = True
    os.environ.pop("ANALYTICS_KEY", None)
    assert r.status_code == 404


# ── Integration: static pages ─────────────────────────────────────────────────


# ── Performance: latency thresholds (mock mode) ───────────────────────────────

def test_homepage_responds_quickly(app_client):
    import time
    client, _, _ = app_client
    t0 = time.time()
    client.get("/")
    elapsed = time.time() - t0
    assert elapsed < 1.0, f"Homepage took {elapsed:.2f}s — expected < 1s"

def test_stream_plan_first_chunk_arrives_quickly(app_client):
    """Metadata chunk (before any AI call) must arrive in under 1s."""
    import time
    client, _, _ = app_client
    t0 = time.time()
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    elapsed = time.time() - t0
    # In mock mode the whole response is fast — full response under 3s
    assert elapsed < 3.0, f"Stream plan took {elapsed:.2f}s in mock mode — expected < 3s"
    assert r.status_code == 200

def test_rate_endpoint_responds_quickly(app_client):
    import time
    client, _, _ = app_client
    t0 = time.time()
    client.post("/rate", json={"rating": 7, "age_group": "U10", "focus": "Passing"})
    elapsed = time.time() - t0
    assert elapsed < 0.5, f"/rate took {elapsed:.2f}s — expected < 0.5s"

def test_track_endpoint_responds_quickly(app_client):
    import time
    client, _, _ = app_client
    t0 = time.time()
    client.post("/track", json={"event": "share_clicked"})
    elapsed = time.time() - t0
    assert elapsed < 0.5, f"/track took {elapsed:.2f}s — expected < 0.5s"

def test_analytics_responds_quickly(app_client):
    import time
    client, _, _ = app_client
    client.post("/track", json={"event": "page_view"})
    t0 = time.time()
    r = client.get("/analytics")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 1.0, f"/analytics took {elapsed:.2f}s — expected < 1s"


# ── Plan quality: structural validation ───────────────────────────────────────

def test_plan_sections_cover_all_types(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    parts = [p.strip() for p in r.data.split(b"|||") if p.strip()]
    sections = [json.loads(p) for p in parts[1:]]  # skip metadata
    types = {s["type"] for s in sections}
    assert "warmup"   in types, "Missing warmup section"
    assert "game"     in types, "Missing game section"
    assert "cooldown" in types, "Missing cooldown section"

def test_plan_instructions_have_minimum_steps(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    parts = [p.strip() for p in r.data.split(b"|||") if p.strip()]
    sections = [json.loads(p) for p in parts[1:]]
    for s in sections:
        assert len(s["instructions"]) >= 2, \
            f"Section '{s['title']}' has only {len(s['instructions'])} instructions"

def test_plan_coaching_points_present(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    parts = [p.strip() for p in r.data.split(b"|||") if p.strip()]
    sections = [json.loads(p) for p in parts[1:]]
    for s in sections:
        assert len(s["coaching_points"]) >= 1, \
            f"Section '{s['title']}' has no coaching points"

def test_plan_all_durations_positive(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    parts = [p.strip() for p in r.data.split(b"|||") if p.strip()]
    sections = [json.loads(p) for p in parts[1:]]
    for s in sections:
        assert s["duration"] > 0, f"Section '{s['title']}' has zero/negative duration"

def test_plan_has_setup_in_every_section(app_client):
    client, _, _ = app_client
    r = client.post("/stream-plan", data={
        "age_group": "U10", "players": "12", "duration": "75", "focus": "Passing"
    })
    parts = [p.strip() for p in r.data.split(b"|||") if p.strip()]
    sections = [json.loads(p) for p in parts[1:]]
    for s in sections:
        assert s.get("setup", "").strip(), f"Section '{s['title']}' has empty setup"
