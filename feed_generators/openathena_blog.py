"""Generate a feed for the Open Athena blog listing page."""

import sys
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from utils import (
    fetch_content,
    generate_rss_feed,
    parse_date,
    save_rss_feed,
    setup_logging,
    validate_article,
)

logger = setup_logging(__name__)

BLOG_URL = "https://openathena.ai/blog/"
# The listing renders each post as "<date> · <author>".
META_SEPARATOR = "·"


def extract_text(element):
    """Return an element's text with collapsed whitespace."""
    if element is None:
        return ""
    return " ".join(element.get_text().split())


def parse_blog_row(row):
    """Build an article dict from a single listing card."""
    href = row.get("href")
    if not href:
        return None
    link = urljoin(BLOG_URL, href)

    title = extract_text(row.select_one(".blog-row-title"))
    summary = extract_text(row.select_one(".blog-row-summary"))
    meta = extract_text(row.select_one(".blog-row-meta"))

    date_text, separator, author_text = meta.partition(META_SEPARATOR)
    date = parse_date(date_text.strip()) if date_text else None
    if date is None:
        logger.warning(f"Could not parse the publication date of {link}: {meta!r}")

    article = {
        "title": title,
        "link": link,
        "description": summary or title,
        "date": date,
    }

    author = author_text.strip() if separator else ""
    if author:
        article["author"] = author

    # Cards carry zero or more project tags; the first one is the primary label.
    tags = [extract_text(tag) for tag in row.select(".resource-type-tag")]
    tags = [tag for tag in tags if tag]
    if tags:
        article["category"] = tags[0]

    return article


def parse_blog_html(html_content):
    """Extract every blog post from the server-rendered listing page."""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_links = set()

    for row in soup.select("a.blog-row"):
        try:
            article = parse_blog_row(row)
        except (AttributeError, TypeError, ValueError) as error:
            logger.warning(f"Could not parse blog row: {error}")
            continue

        if article is None or article["link"] in seen_links:
            continue

        if not validate_article(article):
            logger.warning(f"Skipping invalid blog row: {article['link']}")
            continue

        articles.append(article)
        seen_links.add(article["link"])

    logger.info(f"Successfully parsed {len(articles)} Open Athena blog posts")
    return articles


def main(feed_name="openathena"):
    """Generate the RSS feed for the Open Athena blog."""
    try:
        html_content = fetch_content(BLOG_URL, timeout=30)
        articles = parse_blog_html(html_content)
        if not articles:
            logger.warning("No blog posts found on the Open Athena blog page")
            return False

        feed = generate_rss_feed(
            articles,
            {
                "title": "Open Athena Blog",
                "description": "Latest blog posts from Open Athena",
                "link": BLOG_URL,
                "language": "en",
                "author": {"name": "Open Athena"},
                "subtitle": "Research and engineering posts from Open Athena",
                "sort_reverse": False,
                "date_field": "date",
            },
        )
        save_rss_feed(feed, {"feed_name": feed_name, "pretty": True})
        logger.info(f"Successfully generated RSS feed with {len(articles)} articles")
        return True
    except Exception as error:
        logger.error(f"Failed to generate RSS feed: {error}")
        return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
