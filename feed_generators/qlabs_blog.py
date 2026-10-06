"""Generate a feed from Q's research links on its homepage."""

import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from utils import generate_rss_feed, save_rss_feed, setup_logging, validate_article

logger = setup_logging(__name__)
HOME_URL = "https://qlabs.sh/"


def parse_home_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_links = set()
    for section in soup.select(".work .theme"):
        heading = section.find("h2")
        category = heading.get_text(" ", strip=True) if heading else "Research"
        # Each paragraph's first link is the work; later links are social mirrors.
        for paragraph in section.find_all("p"):
            anchor = paragraph.find("a", href=True)
            if anchor is None:
                continue
            link = urljoin(HOME_URL, anchor["href"])
            if urlparse(link).scheme not in {"http", "https"} or link in seen_links:
                continue
            # Preserve inline superscripts without introducing spaces into 10^7.
            for br in anchor.find_all("br"):
                br.replace_with(" ")
            for sup in anchor.find_all("sup"):
                sup.replace_with("^" + sup.get_text())
            title = " ".join(anchor.get_text().split())
            article = {
                "title": title,
                "link": link,
                "description": f"{category}: {title}",
                "category": category,
            }
            # The homepage provides no publication dates; do not invent them.
            if not validate_article(article, require_date=False):
                raise ValueError(f"Invalid research entry: {link}")
            articles.append(article)
            seen_links.add(link)
    if not articles:
        raise ValueError("No research links found on Q's homepage")
    return articles


def main(feed_name="qlabs"):
    try:
        response = requests.get(HOME_URL, timeout=30)
        response.raise_for_status()
        articles = parse_home_html(response.content.decode("utf-8"))
        feed = generate_rss_feed(
            # FeedGenerator prepends entries; reverse to retain homepage order.
            list(reversed(articles)),
            {
                "title": "Q — Research",
                "description": "Research links from Q (qlabs.sh). Publication dates are omitted because the homepage does not provide them.",
                "link": HOME_URL,
                "language": "en",
            },
        )
        save_rss_feed(feed, {"feed_name": feed_name, "pretty": True})
        logger.info("Successfully generated RSS feed with %s entries", len(articles))
        return True
    except Exception as error:
        logger.error("Failed to generate RSS feed: %s", error)
        return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
