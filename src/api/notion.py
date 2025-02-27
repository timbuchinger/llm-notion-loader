import logging
import time
from typing import Any, Dict, List, Optional

import requests

from ..config import Config
from ..utils.stats import SyncStats, get_stats

logger = logging.getLogger(__name__)


class NotionAPI:
    def __init__(self, stats: Optional[SyncStats] = None):
        self.api_token = Config.REQUIRED_ENV_VARS["NOTION_API_TOKEN"]
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Notion-Version": "2022-06-28",
        }
        self.stats = stats or get_stats()

    def _handle_rate_limit(self, response: requests.Response) -> None:
        """Handle rate limit response from Notion API.

        Args:
            response: Response object from request
        """
        if response.status_code == 429:
            self.stats.increment_counter("rate_limit_hits")
            retry_after = int(response.headers.get("Retry-After", "5"))
            self.stats.rate_limit_wait_time += retry_after
            logger.warning(f"Rate limit hit, waiting {retry_after} seconds")
            time.sleep(retry_after)

    def get_page_content(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the content of a Notion page.

        Args:
            page_id: ID of the Notion page

        Returns:
            Page content as a dictionary, or None if the request fails
        """
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
        while True:
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                self._handle_rate_limit(response)
                continue
            else:
                logger.error(f"Failed to retrieve page content: {response.status_code}")
                logger.error(response.text)
                return None

    def search_pages(self) -> List[Dict[str, Any]]:
        """Search for all pages in the workspace.

        Returns:
            List of page objects
        """
        url = "https://api.notion.com/v1/search/"
        data = {
            "query": "",
            "filter": {"value": "page", "property": "object"},
            "sort": {"direction": "ascending", "timestamp": "last_edited_time"},
        }

        while True:
            response = requests.post(url, headers=self.headers, json=data)
            if response.status_code == 200:
                return response.json().get("results", [])
            elif response.status_code == 429:
                self._handle_rate_limit(response)
                continue
            else:
                logger.error(f"Failed to load page list: {response.status_code}")
                logger.error(response.text)
                raise Exception("Failed to retrieve page list")

    @staticmethod
    def parse_rich_text(rich_text: List[Dict[str, Any]]) -> str:
        """Parse Notion's rich text format into plain text.

        Args:
            rich_text: List of rich text objects from Notion API

        Returns:
            Plain text content
        """
        return "".join([text.get("text", {}).get("content", "") for text in rich_text])

    def parse_block_content(self, block: Dict[str, Any]) -> str:
        """Parse a Notion block into markdown format.

        Args:
            block: Notion block object

        Returns:
            Markdown formatted string
        """
        block_type = block.get("type")

        if block_type == "paragraph":
            paragraph = block.get("paragraph", {}).get("rich_text", [])
            text = self.parse_rich_text(paragraph)
            return text

        elif block_type == "heading_1":
            heading = block.get("heading_1", {}).get("rich_text", [])
            return f"# {self.parse_rich_text(heading)}"

        elif block_type == "heading_2":
            heading = block.get("heading_2", {}).get("rich_text", [])
            return f"## {self.parse_rich_text(heading)}"

        elif block_type == "heading_3":
            heading = block.get("heading_3", {}).get("rich_text", [])
            return f"### {self.parse_rich_text(heading)}"

        elif block_type == "bulleted_list_item":
            bullet = block.get("bulleted_list_item", {}).get("rich_text", [])
            return f"* {self.parse_rich_text(bullet)}"

        elif block_type == "numbered_list_item":
            bullet = block.get("numbered_list_item", {}).get("rich_text", [])
            return f"* {self.parse_rich_text(bullet)}"

        elif block_type == "divider":
            return "---"

        else:
            logger.info(f"Block type not supported: {block_type}")
            return ""

    def get_page_title(self, page: Dict[str, Any]) -> str:
        """Extract the title from a Notion page object.

        Args:
            page: Notion page object

        Returns:
            Page title or "Untitled" if not found
        """
        try:
            return (
                page.get("properties", {})
                .get("title", {})
                .get("title", [])[0]
                .get("plain_text", "Untitled")
            )
        except:
            logger.info("Title not found, using 'Untitled'")
            return "Untitled"

    def get_page_markdown(self, page_id: str) -> Optional[str]:
        """Get the full markdown content of a page.

        Args:
            page_id: ID of the Notion page

        Returns:
            Markdown formatted content or None if retrieval fails
        """
        content = self.get_page_content(page_id)
        if not content:
            return None

        markdown_lines = []
        for block in content.get("results", []):
            markdown_lines.append(self.parse_block_content(block))

        return "\n".join(line for line in markdown_lines if line)
