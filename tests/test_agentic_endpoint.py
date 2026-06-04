import json

from agentic_endpoint import app


def test_extract_json_object_accepts_fenced_json():
    payload = app._extract_json_object(
        '```json\n{"summary": "ok", "findings": [], "next_actions": [], "risk_level": "low"}\n```'
    )

    assert payload["summary"] == "ok"
    assert payload["risk_level"] == "low"


def test_lambda_handler_uses_autogen_orchestrator_without_live_openai(monkeypatch):
    def fake_agent(agent_name, profile, payload, prior_outputs, retrieved_context, max_output_tokens, api_key):
        return {
            "summary": f"{agent_name} reviewed the event.",
            "findings": ["Relevant RAG context was retrieved."],
            "next_actions": ["Continue care coordination."],
            "risk_level": "medium",
        }

    def fake_final(payload, agent_outputs, retrieved_context, max_output_tokens, api_key):
        return {
            "case_summary": "Patient event was reviewed by the agent crew.",
            "care_team_consensus": "Continue urgent coordination and monitoring.",
            "recommended_actions": ["Escalate to clinical review.", "Prepare bedside handoff."],
            "signals_to_monitor": ["oxygen_saturation", "blood_pressure"],
            "escalation_level": "urgent",
            "handoff": "Share agent findings with the care team.",
        }

    monkeypatch.setattr(app, "autogen_is_available", lambda: True)
    monkeypatch.setattr(app, "get_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(app, "run_autogen_agent", fake_agent)
    monkeypatch.setattr(app, "run_autogen_final_inference", fake_final)

    response = app.lambda_handler(
        {
            "body": json.dumps(
                {
                    "patient_context": {"age": 64, "location": "emergency department"},
                    "chief_concern": "Shortness of breath and chest pressure.",
                    "vitals": {"heart_rate": 118, "oxygen_saturation": 89},
                    "requested_inference": "Coordinate triage and handoff priorities.",
                }
            )
        },
        None,
    )
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["orchestrator"] == "autogen"
    assert [agent["agent_id"] for agent in body["agents"]] == ["agent_1", "agent_2", "agent_3"]
    assert [agent["agent"] for agent in body["agents"]] == ["hospital", "doctor", "nurse"]
    assert body["inference"]["escalation_level"] == "urgent"
    assert body["retrieved_context"]
