import re
from datetime import datetime

import pytz
from bs4 import BeautifulSoup
from utils import (
    fetch_content,
    generate_rss_feed,
    save_rss_feed,
    setup_logging,
    validate_article,
)

logger = setup_logging(__name__)

RESEARCH_URL = "https://tilderesearch.com/research"
ARTICLE_URL_PATTERN = re.compile(
    r"^https://blog\.tilderesearch\.com/(?:blog|vignettes)/"
)
DATE_PATTERN = re.compile(r"^\d{1,2}\.\d{1,2}\.(?:\d{2}|\d{4})$")
CATEGORIES = {"Announcement", "Technical Release", "Vignette"}


def parse_tilde_date(date_text):
    """Parse the dotted dates used on Tilde's research cards."""
    year_format = "%Y" if len(date_text.rsplit(".", 1)[-1]) == 4 else "%y"
    return datetime.strptime(date_text, f"%m.%d.{year_format}").replace(
        tzinfo=pytz.UTC
    )


def extract_card_text(card):
    """Return the title, description, category, and date from a research card."""
    texts = [
        " ".join(element.stripped_strings)
        for element in card.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"])
    ]
    texts = [text for text in texts if text]

    date_text = next(
        (text for text in reversed(texts) if DATE_PATTERN.fullmatch(text)), None
    )
    category = next((text for text in texts if text in CATEGORIES), None)

    metadata = {"Read More", date_text, category}
    content = [text for text in texts if text not in metadata]
    if not content or not date_text:
        return None

    return {
        "title": content[0],
        "description": content[1] if len(content) > 1 else content[0],
        "category": category,
        "date": parse_tilde_date(date_text),
    }


def parse_research_html(html_content):
    """Extract research posts from Tilde's server-rendered Framer cards."""
    if "charset=\"utf-8\"" in html_content[:1000].lower():
        try:
            html_content = html_content.encode("latin-1").decode("utf-8")
        except UnicodeError:
            pass

    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_links = set()

    for card in soup.find_all("a", href=ARTICLE_URL_PATTERN):
        link = card["href"]
        if link in seen_links:
            continue

        try:
            article = extract_card_text(card)
            if not article:
                logger.warning(f"Could not parse research card: {link}")
                continue

            article["link"] = link
            if not article["category"]:
                article.pop("category")

            if validate_article(article):
                articles.append(article)
                seen_links.add(link)
        except (TypeError, ValueError) as error:
            logger.warning(f"Could not parse research card {link}: {error}")

    logger.info(f"Successfully parsed {len(articles)} Tilde research posts")
    return articles


def main(feed_name="tilde_research"):
    """Generate the RSS feed for Tilde Research."""
    try:
        html_content = fetch_content(RESEARCH_URL, timeout=30)
        articles = parse_research_html(html_content)
        if not articles:
            logger.warning("No research posts found on the Tilde Research page")
            return False

        feed = generate_rss_feed(
            articles,
            {
                "title": "Tilde Research",
                "description": "Latest technical releases and vignettes from Tilde Research",
                "link": RESEARCH_URL,
                "language": "en",
                "author": {"name": "Tilde Research"},
                "subtitle": "Research publications from Tilde Research",
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
    main()
