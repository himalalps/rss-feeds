"""Generate a feed for the Goodfire research index."""

import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from utils import (
    generate_rss_feed,
    parse_date,
    save_rss_feed,
    setup_logging,
    validate_article,
)

logger = setup_logging(__name__)

RESEARCH_URL = "https://www.goodfire.com/research"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)
# Each card renders its byline as "<author> · <date>" inside .index-meta.
META_SEPARATOR = "·"


def fetch_research_html():
    """Fetch the index, decoding as UTF-8.

    The site serves `text/html` without a charset, so `response.text` would
    fall back to ISO-8859-1 and mangle every non-ASCII character.
    """
    try:
        response = requests.get(
            RESEARCH_URL, headers={"User-Agent": USER_AGENT}, timeout=30
        )
        response.raise_for_status()
        return response.content.decode("utf-8")
    except requests.RequestException as error:
        logger.error(f"Error fetching content from {RESEARCH_URL}: {error}")
        raise


def extract_text(element):
    """Return an element's text with collapsed whitespace."""
    if element is None:
        return ""
    return " ".join(element.get_text().split())


def parse_meta(meta_element):
    """Split an .index-meta line into its author and date halves."""
    if meta_element is None:
        return "", None

    parts = []
    for span in meta_element.find_all("span"):
        # The "·" between author and date is decorative and aria-hidden.
        if span.get("aria-hidden") == "true":
            continue
        text = extract_text(span)
        if text and text != META_SEPARATOR:
            parts.append(text)

    if not parts:
        return "", None

    # The date is the trailing span; anything before it is the author line.
    date = parse_date(parts[-1])
    if date is None:
        return " ".join(parts), None
    return " ".join(parts[:-1]), date


def parse_index_item(item):
    """Build an article dict from a single research card."""
    href = item.get("href")
    if not href:
        return None
    link = urljoin(RESEARCH_URL, href)

    title = extract_text(item.select_one("h2"))
    author, date = parse_meta(item.select_one(".index-meta"))
    tags = [extract_text(tag) for tag in item.select(".tag-tile")]
    tags = [tag for tag in tags if tag]

    if date is None:
        logger.warning(f"Could not parse the publication date of {link}")

    # The cards carry no summary, so the byline and tags are the description.
    description = " — ".join(part for part in [", ".join(tags), author] if part)

    article = {
        "title": title,
        "link": link,
        "description": description or title,
        "date": date,
    }

    if author:
        article["author"] = author
    if tags:
        article["category"] = tags[0]

    return article


def parse_research_html(html_content):
    """Extract every research post from the server-rendered index."""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_links = set()

    for item in soup.select("a.index-item"):
        try:
            article = parse_index_item(item)
        except (AttributeError, TypeError, ValueError) as error:
            logger.warning(f"Could not parse research item: {error}")
            continue

        if article is None or article["link"] in seen_links:
            continue

        if not validate_article(article):
            logger.warning(f"Skipping invalid research item: {article['link']}")
            continue

        articles.append(article)
        seen_links.add(article["link"])

    logger.info(f"Successfully parsed {len(articles)} Goodfire research posts")
    return articles


def main(feed_name="goodfire_research"):
    """Generate the RSS feed for Goodfire research."""
    try:
        html_content = fetch_research_html()
        articles = parse_research_html(html_content)
        if not articles:
            logger.warning("No research posts found on the Goodfire research page")
            return False

        feed = generate_rss_feed(
            articles,
            {
                "title": "Goodfire Research",
                "description": "Latest interpretability research from Goodfire",
                "link": RESEARCH_URL,
                "language": "en",
                "author": {"name": "Goodfire"},
                "subtitle": "Interpretability research from Goodfire",
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
