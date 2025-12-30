import time
from src.service.knowledge_base import KnowledgeBaseServiceMarkdown
import unittest


class TestKBService(unittest.TestCase):
    kb_service = None  # Class-level attribute

    @classmethod
    def setUpClass(cls):
        """Run once before all tests in this class."""
        start_time = time.time()
        cls.kb_service = KnowledgeBaseServiceMarkdown()
        end_time = time.time()
        print(
            f"Time taken to load embedding model: {end_time - start_time} seconds")

    def test_get_stats(self):
        self.assertIsNotNone(self.kb_service.model)
        self.assertGreater(len(self.kb_service.chunks), 0)
        stats = self.kb_service.get_stats()
        self.assertGreater(stats["total_chunks"], 0)
        self.assertGreater(stats["total_sources"], 0)
        self.assertGreater(stats["embedding_dimensions"], 0)
        # Print stats
        print(f"Knowledge Base Stats: {stats}")

    def test_query_1(self):
        query = "What is OLTP/ OLAP and their use cases?"
        search_results = self.kb_service.search(query, top_k=2)
        self.assertGreater(len(search_results), 0)
        print(f"Search results for '{query}': {len(search_results)}")

    def test_query_2(self):
        query = "How to prepare for a Java interview?"
        search_results = self.kb_service.search(query, top_k=8)
        self.assertGreater(len(search_results), 0)
        print(f"Search results for '{query}': {len(search_results)}")


if __name__ == "__main__":
    unittest.main()
