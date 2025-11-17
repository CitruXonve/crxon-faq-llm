import json
from fastapi.testclient import TestClient

from src.main import app


def test_chat_dataflow():
    """Test: User question -> AI response -> case-by-case handling"""

    # Use TestClient as context manager to ensure startup_event is called
    with TestClient(app) as client:
        try:
            resp = client.post("/api/chat", json={
                "message": "What is OLTP/ OLAP and their use cases?"
            })

            assert resp is not None
            assert resp.status_code == 201
            assert resp.json()["status"] == "success"
            assert len(resp.json()["session_id"]) == 36
            assert len(resp.json()["messages"]) > 0
            assert resp.json()["messages"][-1]["type"] == "ai"

            session_id = resp.json()["session_id"]
            request_body = {
                "session_id": session_id,
                "message": "What is multi-threading in Python?"
            }
            resp = client.post("/api/chat", json=request_body)

            print("Request body:", json.dumps(request_body, indent=4))
            print("Status code:", resp.status_code)

            resp = client.get(f"/api/chat/{session_id}")

            assert resp is not None
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"
            assert resp.json()["session_id"] == session_id
            assert len(resp.json()["messages"]) == 4
            assert resp.json()["messages"][-1]["type"] == "ai"

            print("Fetched history:", len(resp.json()[
                  "messages"]), json.dumps(resp.json(), indent=4))

        except Exception as e:
            print(f"Error: {e}")
            raise


if __name__ == "__main__":
    test_chat_dataflow()
