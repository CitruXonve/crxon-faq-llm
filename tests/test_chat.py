import json
from fastapi.testclient import TestClient
import unittest
from src.main import app


class TestChat(unittest.TestCase):
    """Test: User question -> AI response -> case-by-case handling"""

    def test_chat_dataflow(self):
        """Use TestClient as context manager to ensure startup_event is called"""
        with TestClient(app) as client:
            try:
                resp = client.post("/api/chat", json={
                    "message": "What is OLTP/ OLAP and their use cases?"
                })

                self.assertIsNotNone(resp)
                self.assertEqual(resp.status_code, 201)
                self.assertEqual(resp.json()["status"], "success")
                self.assertEqual(len(resp.json()["session_id"]), 36)
                self.assertGreater(len(resp.json()["messages"]), 0)
                self.assertEqual(resp.json()["messages"][-1]["type"], "ai")

                session_id = resp.json()["session_id"]
                request_body = {
                    "session_id": session_id,
                    "message": "What is multi-threading in Python?"
                }
                resp = client.post("/api/chat", json=request_body)

                print("Request body:", json.dumps(request_body, indent=4))
                print("Status code:", resp.status_code)

                resp = client.get(f"/api/chat/{session_id}")

                self.assertIsNotNone(resp)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["status"], "success")
                self.assertEqual(resp.json()["session_id"], session_id)
                self.assertEqual(len(resp.json()["messages"]), 4)
                self.assertEqual(resp.json()["messages"][-1]["type"], "ai")

                self.assertEqual(len(resp.json()["messages"]), 4)

            except Exception as e:
                print(f"Error: {e}")
                raise


if __name__ == "__main__":
    unittest.main()
