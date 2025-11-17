from uuid import uuid4
from collections import defaultdict
from langchain.messages import AnyMessage


class SessionService:
    def __init__(self):
        # session_id -> {chat_history: list[dict], user_id: str}
        self.data = defaultdict(lambda: {
            "chat_history": [],
            "user_id": None
        })

    def create_session(self) -> str:
        """Create a new session"""
        session_id = str(uuid4())
        return session_id

    def get_history(self, session_id: str) -> list[AnyMessage]:
        """Retrieve chat history for a session"""
        return self.data[session_id].get("chat_history", [])

    def set_history(self, session_id: str, chat_history: list[AnyMessage]) -> None:
        """Set chat history for a session"""
        self.data[session_id]["chat_history"].clear()
        self.data[session_id]["chat_history"].extend(chat_history)
