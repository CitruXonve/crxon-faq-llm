import time
from src.service.knowledge_base import KnowledgeBaseServiceMarkdown


def test_kb_service():
    print("Testing knowledge base service...")
    start_time = time.time()
    kb_service = KnowledgeBaseServiceMarkdown()
    assert kb_service.model is not None
    end_time = time.time()
    print(
        f"Time taken to load embedding model: {end_time - start_time} seconds")
    assert len(kb_service.chunks) > 0

    # Print stats
    stats = kb_service.get_stats()
    print(f"Knowledge Base Stats: {stats}")

    # Example search
    query = "What is multi-threading in Python?"
    search_results = kb_service.search(query)
    assert len(search_results) > 0
    print(
        f"Search results for '{query}': {len(search_results)}")

    query = "What is OLTP/ OLAP and their use cases?"
    search_results = kb_service.search(
        query, top_k=2)
    assert len(search_results) > 0
    print(
        f"Search results for '{query}': {len(search_results)}")

    query = "How to prepare for a Java interview?"
    search_results = kb_service.search(query, top_k=8)
    assert len(search_results) > 0
    print(f"Search results for '{query}': {len(search_results)}")


if __name__ == "__main__":
    test_kb_service()
