import logging
import os
from typing import Any
import requests
from bs4 import BeautifulSoup
import json

from src.config.settings import settings

logger = logging.getLogger(__name__)


class GitHubRepoFetchService:
    def __init__(self, repository_url: str, raw_content_url: str):
        self.repository_url = repository_url
        self.raw_content_url = raw_content_url

    def fetch_post_list(self) -> list[dict]:
        response = requests.get(self.repository_url)
        scripts = BeautifulSoup(response.text, 'html.parser').find_all(
            'script', type='application/json')
        if len(scripts) < 1 or scripts[-1].text is None:
            raise ValueError("No scripts found")
        posts = json.loads(scripts[-1].text)
        if "payload" not in posts or "tree" not in posts["payload"] or "items" not in posts["payload"]["tree"]:
            raise ValueError("No content data field found")
        repos = posts["payload"]["tree"]["items"]
        return repos

    def fetch_post_content(self, relative_path: str) -> str:
        response = requests.get(self.raw_content_url + relative_path)
        if response.status_code != 200:
            raise ValueError(
                f"Failed to fetch post content: {response.status_code}")
        return response.text

    def save_post_content(self, name: str, content: str) -> bool:
        if not os.path.exists(os.path.join(settings.KB_DIRECTORY, name)):
            with open(os.path.join(settings.KB_DIRECTORY, name), "w") as f:
                f.write(content)
            logger.info(
                f"Post content written to {os.path.join(settings.KB_DIRECTORY, name)}")
            return True
        else:
            logger.info(
                f"Post content already exists in {os.path.join(settings.KB_DIRECTORY, name)}")
            return False

    def save_all_posts(self) -> None:
        post_list = self.fetch_post_list()
        existing_count = 0
        saved_count = 0
        for post in post_list:
            post_content = self.fetch_post_content(post["path"])
            saved = self.save_post_content(post["name"], post_content)
            if saved:
                saved_count += 1
            else:
                existing_count += 1
        logger.debug(
            f"Saved {saved_count} posts; {existing_count} posts already exist")
        print(
            f"Saved {saved_count} posts; {existing_count} posts already exist")
