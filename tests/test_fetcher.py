import os
import unittest
import uuid
from src.config.settings import settings
from src.service.fetch_service import GitHubRepoFetchService


class TestGitHubRepoFetcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Run once before all tests in this class."""
        cls.fetcher = GitHubRepoFetchService(
            repository_url="https://github.com/CitruXonve/devblog/tree/master/source/_posts",
            raw_content_url="https://raw.githubusercontent.com/CitruXonve/devblog/refs/heads/master/")

    def test_fetch_post_list(self):
        post_list = self.fetcher.fetch_post_list()
        self.assertIsInstance(post_list, list)
        self.assertGreater(len(post_list), 0)

    def test_fetch_post_content(self):
        post_content = self.fetcher.fetch_post_content(
            "/source/_posts/k8s-entry.md")
        self.assertIsNotNone(post_content)
        self.assertGreater(len(post_content), 0)
        self.assertIsInstance(post_content, str)
        lines = post_content.split("\n")
        self.assertGreater(len(lines), 3)
        self.assertEqual(lines[0], "---")
        self.assertTrue(lines[1].startswith("title:"))
        self.assertTrue(lines[2].startswith("tags:"))

    def test_save_post_content(self):
        random_name = f"test_{str(uuid.uuid4())}.md"
        self.assertFalse(os.path.exists(
            os.path.join(settings.KB_DIRECTORY, random_name)))
        saved = self.fetcher.save_post_content(random_name, "test content")
        self.assertTrue(saved)
        self.assertTrue(os.path.exists(
            os.path.join(settings.KB_DIRECTORY, random_name)))
        os.remove(os.path.join(settings.KB_DIRECTORY, random_name))


if __name__ == "__main__":
    unittest.main()
