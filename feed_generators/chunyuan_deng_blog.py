import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from utils import generate_rss_feed, save_rss_feed, setup_logging, validate_article

logger = setup_logging(__name__)
ARCHIVE_URL = "https://charlesdddd.github.io/blog/archive.html"


def english_text(element):
    """Use the default English text without concatenating hidden translations."""
    if element is None:
        return ""
    english = element.select_one(".lang-en")
    return " ".join((english if english is not None else element).stripped_strings)


def parse_archive_html(html_content):
    """Extract listed posts; HTML comments (unlisted posts) are not selected."""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_links = set()
    for card in soup.select("a.blog-item[href]"):
        link = urljoin(ARCHIVE_URL, card["href"])
        if link in seen_links or urlparse(link).scheme not in {"http", "https"}:
            continue
        date_text = english_text(card.select_one(".blog-item-date"))
        # The source provides only a month: use its first day at midnight UTC,
        # a stable approximation rather than the date this script happens to run.
        date = datetime.strptime(date_text, "%B %Y").replace(tzinfo=timezone.utc)
        title = english_text(card.select_one(".blog-item-title"))
        article = {
            "title": title,
            "link": link,
            "description": english_text(card.select_one(".blog-item-desc")) or title,
            "date": date,
        }
        if not validate_article(article):
            raise ValueError(f"Invalid archive entry: {link}")
        articles.append(article)
        seen_links.add(link)
    return articles


def main(feed_name="chunyuan_deng"):
    """Generate Chunyuan Deng's archive feed for the daily feed runner."""
    try:
        response = requests.get(ARCHIVE_URL, timeout=30)
        response.raise_for_status()
        # Decode explicitly: this site's HTTP headers may omit the charset.
        articles = parse_archive_html(response.content.decode("utf-8"))
        if not articles:
            raise ValueError("No blog posts found in the archive")
        feed = generate_rss_feed(
            articles,
            {
                "title": "Chunyuan Deng — Blog",
                "description": "Blog posts from Chunyuan Deng. Publication dates are approximate: the archive provides only the month, represented here as its first day in UTC.",
                "link": ARCHIVE_URL,
                "language": "en",
                "author": {"name": "Chunyuan Deng"},
                # FeedGenerator prepends entries, so ascending input yields newest first.
                "sort_reverse": False,
                "date_field": "date",
            },
        )
        save_rss_feed(feed, {"feed_name": feed_name, "pretty": True})
        logger.info("Successfully generated RSS feed with %s articles", len(articles))
        return True
    except Exception as error:
        logger.error("Failed to generate RSS feed: %s", error)
        return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
