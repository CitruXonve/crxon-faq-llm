import json
import time
import asyncio
import unittest
from src.service.llm_service import ClaudeLLMService
from src.service.knowledge_base import KnowledgeBaseServiceMarkdown


class TestLLM(unittest.IsolatedAsyncioTestCase):
    llm_service = None  # Class-level attribute

    @classmethod
    def setUpClass(cls):
        """Run once before all tests in this class."""
        start_time = time.time()
        # kb_service = KnowledgeBaseServiceMarkdown()
        # cls.llm_service = ClaudeLLMService(kb_service)
        cls.llm_service = ClaudeLLMService(KnowledgeBaseServiceMarkdown())
        end_time = time.time()
        print(
            f"Time taken to initialize LLM service: {(end_time - start_time):.2f} seconds")
        print("Testing LLM context prompt...")

    async def _sent_user_message(self, user_message: str, start_time: float, chat_history: list[dict]):
        print(f"Sending user message: {user_message}")
        resp = await self.llm_service.generate_response(user_message, chat_history)
        assert resp["messages"] is not None and len(resp["messages"]) > 0
        chat_history.clear()
        chat_history.extend(resp["messages"])
        end_time = time.time()
        print(
            f"Time taken to generate response: {(end_time - start_time):.2f} seconds")
        print("LLM response length:", len(resp["messages"][-1].content))
        print(
            "LLM confidence:", json.dumps({key: value for key, value in resp.items() if key != "messages"}, indent=4) if type(resp) is dict else resp)
        return end_time

    async def test_claude_llm_context_prompt(self):
        chat_history = []
        start_time = time.time()
        end_time = await self._sent_user_message("What is multi-threading in Python?", start_time, chat_history)
        self.assertEqual(len(chat_history), 2)
        print(
            f"Time taken to send user message: {(end_time - start_time):.2f} seconds")
        print(
            f"Chat response: {len(chat_history)}", json.dumps({"role": chat_history[-1].type, "content": chat_history[-1].content}, indent=4))
        start_time = time.time()
        end_time = await self._sent_user_message("What is OLTP/ OLAP and their use cases?", start_time, chat_history)
        self.assertEqual(len(chat_history), 4)
        print(
            f"Time taken to send user message: {(end_time - start_time):.2f} seconds")
        print(
            f"Chat response: {len(chat_history)}", json.dumps({"role": chat_history[-1].type, "content": chat_history[-1].content}, indent=4))
        start_time = time.time()
        end_time = await self._sent_user_message("How to prepare for a Java interview?", start_time, chat_history)
        self.assertEqual(len(chat_history), 6)
        print(
            f"Time taken to send user message: {(end_time - start_time):.2f} seconds")
        print(
            f"Chat response: {len(chat_history)}", json.dumps({"role": chat_history[-1].type, "content": chat_history[-1].content}, indent=4))


# if __name__ == "__main__":
#     asyncio.run(unittest.main())
