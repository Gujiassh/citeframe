"""Persist production policy transitions, serialize, then consume with the production Web parser."""
import shutil
import subprocess
from pathlib import Path
from sqlalchemy import select
from ai_pdf_api.models import ResearchEvent
from ai_pdf_api.services.research.research_artifacts import serialize_sse_event
from test_research_autonomy import publish, test_conflicts_are_retained_and_queue_synthesis_without_human_gate as exercise_conflict


def consume(db, run_id, tmp_path):
    events = list(db.scalars(select(ResearchEvent).where(ResearchEvent.run_id == run_id).order_by(ResearchEvent.seq)))
    wire = tmp_path / "events.sse"
    wire.write_text("".join(serialize_sse_event(e) for e in events), encoding="utf-8")
    web = Path(__file__).resolve().parents[2] / "web"
    result = subprocess.run([shutil.which("node"), "--import", "tsx", "scripts/check-research-sse.mjs", str(wire)],
        cwd=web, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_automatic_plan_production_event_consumed_by_web(research_app, tmp_path):
    client, db, context = research_app
    run, _ = publish(client, db, context)
    assert "plan_approval" in consume(db, run.id, tmp_path)


def test_automatic_conflict_production_event_consumed_by_web(research_worker_db, tmp_path):
    exercise_conflict(research_worker_db)
    assert "conflict_resolution" in consume(research_worker_db.db, research_worker_db.run.id, tmp_path)
