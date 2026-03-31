import os

import requests
from utils import (
    generate_rss_feed,
    parse_date,
    save_rss_feed,
    setup_logging,
    validate_article,
)

# Set up logging
logger = setup_logging(__name__)

GITHUB_API_URL = "https://api.github.com/repos/leloykun/leloykun.github.io/contents/content/ponder"
GITHUB_API_BRANCH = "prod"
BLOG_BASE_URL = "https://leloykun.github.io/ponder"


def parse_front_matter(content):
    """Parse YAML front matter from a Hugo markdown file.

    Returns a dict of top-level scalar fields only (nested structures are skipped).
    """
    if not content.startswith("---"):
        return {}

    # Find the closing ---
    end_pos = content.find("---", 3)
    if end_pos == -1:
        return {}

    front_matter_text = content[3:end_pos]
    result = {}

    for line in front_matter_text.splitlines():
        # Skip indented lines (nested structures use leading whitespace in YAML)
        if line and (line[0] == " " or line[0] == "\t"):
            continue
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        # Remove surrounding quotes if present
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        elif len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1]
        result[key] = value

    return result


def fetch_ponder_list():
    """Fetch the list of entries in content/ponder from the GitHub API."""
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Mozilla/5.0 (RSS Feed Generator)",
        }
        github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        params = {"ref": GITHUB_API_BRANCH}
        response = requests.get(
            GITHUB_API_URL, headers=headers, params=params, timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching ponder list from GitHub API: {str(e)}")
        raise


def fetch_post_content(download_url):
    """Fetch the raw content of a single post."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (RSS Feed Generator)",
        }
        response = requests.get(download_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.warning(f"Error fetching post content from {download_url}: {str(e)}")
        return None


def fetch_index_md(slug):
    """Fetch the index.md file for a given post slug via the GitHub API."""
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Mozilla/5.0 (RSS Feed Generator)",
        }
        github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        url = f"{GITHUB_API_URL}/{slug}/index.md"
        params = {"ref": GITHUB_API_BRANCH}
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        download_url = data.get("download_url")
        if not download_url:
            return None
        return fetch_post_content(download_url)
    except requests.RequestException as e:
        logger.warning(f"Error fetching index.md for slug '{slug}': {str(e)}")
        return None


def extract_articles(ponder_list):
    """Extract article information from the list of GitHub repository ponder entries."""
    articles = []

    for entry in ponder_list:
        entry_type = entry.get("type", "")
        name = entry.get("name", "")

        # Only process directories (each post is a Hugo page bundle directory)
        if entry_type != "dir":
            continue

        slug = name
        link = f"{BLOG_BASE_URL}/{slug}/"

        try:
            content = fetch_index_md(slug)
            if not content:
                logger.warning(f"Could not fetch index.md for slug: {slug}")
                continue

            front_matter = parse_front_matter(content)

            title = front_matter.get("title", "")
            if not title:
                title = slug.replace("-", " ").title()

            date_str = front_matter.get("date", "")
            date = parse_date(date_str) if date_str else None

            description = (
                front_matter.get("description", "")
                or front_matter.get("summary", "")
                or title
            )

            article = {
                "title": title,
                "link": link,
                "description": description,
                "date": date,
            }

            if validate_article(article):
                articles.append(article)
                logger.info(f"Parsed article: {title}")
            else:
                logger.warning(f"Article failed validation, skipping: {slug}")

        except Exception as e:
            logger.warning(f"Error parsing post '{slug}': {str(e)}")
            continue

    logger.info(f"Successfully parsed {len(articles)} articles")
    return articles


def main(feed_name="leloykun"):
    """Main function to generate RSS feed from leloykun's ponder blog."""
    try:
        logger.info(f"Fetching ponder list from {GITHUB_API_URL}")
        ponder_list = fetch_ponder_list()

        if not ponder_list:
            logger.warning("No entries found in the repository")
            return False

        articles = extract_articles(ponder_list)

        if not articles:
            logger.warning("No valid articles found")
            return False

        feed_config = {
            "title": "leloykun's Ponder",
            "description": "Blog posts from leloykun's Ponder",
            "link": "https://leloykun.github.io/ponder/",
            "language": "en",
            "author": {"name": "Franz Louis Cesista"},
            "subtitle": "leloykun's Ponder blog",
            "sort_reverse": False,
            "date_field": "date",
        }
        feed = generate_rss_feed(articles, feed_config)

        save_config = {
            "feed_name": feed_name,
            "pretty": True,
        }
        save_rss_feed(feed, save_config)

        logger.info(f"Successfully generated RSS feed with {len(articles)} articles")
        return True

    except Exception as e:
        logger.error(f"Failed to generate RSS feed: {str(e)}")
        return False


if __name__ == "__main__":
    main()
