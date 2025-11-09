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
    print(f"Number of chunks: {len(kb_service.chunks)}")
    print(f"Example chunk: {kb_service.chunks[-1].to_dict()}")
    print(f"Example embedding: {kb_service.chunks[-1].embedding}")

    # Print stats
    stats = kb_service.get_stats()
    print(f"Knowledge Base Stats: {stats}")

    # Example search
    # search_results = kb_service.search("What is the capital of France?")
    # print(f"Search results: {search_results}")


if __name__ == "__main__":
    test_kb_service()
