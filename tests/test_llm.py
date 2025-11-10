import json
import time
import asyncio
from src.service.llm_service import ClaudeLLMService
from src.service.knowledge_base import KnowledgeBaseServiceMarkdown


async def sent_user_message(llm_service: ClaudeLLMService, user_message: str, start_time: float, chat_history: list[dict]):
    print(f"Sending user message: {user_message}")
    resp = await llm_service.generate_response(user_message, chat_history)
    assert resp["response"] is not None and len(resp["response"].strip()) > 0
    chat_history.append({
        "role": "user",
        "content": user_message
    })
    chat_history.append({
        "role": "assistant",
        "content": resp["response"]
    })
    end_time = time.time()
    print(
        f"Time taken to generate response: {(end_time - start_time):.2f} seconds")
    print("LLM response length:", len(resp["response"]))
    return end_time


async def test_claude_llm_context_prompt():
    print("Testing LLM context prompt...")
    start_time = time.time()
    kb_service = KnowledgeBaseServiceMarkdown()
    llm_service = ClaudeLLMService(kb_service)
    end_time = time.time()
    print(
        f"Time taken to initialize LLM service: {(end_time - start_time):.2f} seconds")

    chat_history = []
    end_time = await sent_user_message(llm_service, "What is multi-threading in Python?", end_time, chat_history)

    end_time = await sent_user_message(llm_service, "What is OLTP/ OLAP and their use cases?", end_time, chat_history)

    end_time = await sent_user_message(llm_service, "How to prepare for a Java interview?", end_time, chat_history)

    print(
        f"Chat history: {json.dumps(chat_history, indent=4) if type(chat_history) is list else chat_history}")


if __name__ == "__main__":
    asyncio.run(test_claude_llm_context_prompt())
