import os
import re

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

GITHUB_API_URL = "https://api.github.com/repos/Dao-AILab/dao-ailab.github.io/contents/_posts"
BLOG_BASE_URL = "https://dao-lab.ai/blog"


def parse_front_matter(content):
    """Parse YAML front matter from a Jekyll markdown file.

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


def filename_to_url(filename):
    """Convert Jekyll post filename (YYYY-MM-DD-slug.md) to blog URL."""
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+)\.md$", filename)
    if not match:
        return None
    year, month, day, slug = match.groups()
    return f"{BLOG_BASE_URL}/{year}/{month}/{day}/{slug}/"


def fetch_posts_list():
    """Fetch the list of post files from the GitHub API."""
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Mozilla/5.0 (RSS Feed Generator)",
        }
        github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        response = requests.get(GITHUB_API_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching posts list from GitHub API: {str(e)}")
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


def extract_articles(posts_list):
    """Extract article information from the list of GitHub repository post files."""
    articles = []

    for post_info in posts_list:
        filename = post_info.get("name", "")
        download_url = post_info.get("download_url")

        if not filename.endswith(".md") or not download_url:
            continue

        # Construct blog URL from filename
        link = filename_to_url(filename)
        if not link:
            logger.warning(f"Could not construct URL for file: {filename}")
            continue

        try:
            content = fetch_post_content(download_url)
            if not content:
                continue

            front_matter = parse_front_matter(content)

            title = front_matter.get("title", "")
            if not title:
                # Fall back to filename-based title
                match = re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", filename)
                title = (
                    match.group(1).replace("-", " ").title() if match else filename
                )

            date_str = front_matter.get("date", "")
            date = parse_date(date_str) if date_str else None

            description = front_matter.get("description", "") or title

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
                logger.warning(f"Article failed validation, skipping: {filename}")

        except Exception as e:
            logger.warning(f"Error parsing post {filename}: {str(e)}")
            continue

    logger.info(f"Successfully parsed {len(articles)} articles")
    return articles


def main(feed_name="dao_ailab"):
    """Main function to generate RSS feed from Dao-AILab blog."""
    try:
        logger.info(f"Fetching posts list from {GITHUB_API_URL}")
        posts_list = fetch_posts_list()

        if not posts_list:
            logger.warning("No posts found in the repository")
            return False

        articles = extract_articles(posts_list)

        if not articles:
            logger.warning("No valid articles found")
            return False

        feed_config = {
            "title": "Dao-AILab Blog",
            "description": "Latest blog posts from Dao-AILab",
            "link": "https://dao-lab.ai/blog/",
            "language": "en",
            "author": {"name": "Dao-AILab"},
            "subtitle": "Research blog from Dao-AILab",
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
