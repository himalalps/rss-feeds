import re

from bs4 import BeautifulSoup
from utils import (
    fetch_content,
    generate_rss_feed,
    parse_date,
    save_rss_feed,
    setup_logging,
    stable_fallback_date,
    validate_article,
)

# Set up logging
logger = setup_logging(__name__)

BASE_URL = "https://transformer-circuits.pub"
INDEX_URL = BASE_URL


def _make_absolute(href):
    """Convert a relative URL to an absolute one."""
    if not href:
        return None
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def _looks_like_paper_url(href):
    """Return True if the href looks like a link to a paper page."""
    if not href:
        return False
    # Paper URLs contain a 4-digit year segment (with or without a leading slash)
    return bool(re.search(r"(?:^|/)\d{4}/", href))


def _extract_date_from_text(text):
    """Try to extract a date from arbitrary surrounding text."""
    if not text:
        return None
    # Try "Month DD, YYYY" first (most specific)
    m = re.search(r"\b([A-Z][a-z]+ \d{1,2},?\s+\d{4})\b", text)
    if m:
        result = parse_date(m.group(1))
        if result:
            return result
    # Try "Month YYYY" (year only, default to 1st of the month)
    m = re.search(r"\b([A-Z][a-z]+) (\d{4})\b", text)
    if m:
        result = parse_date(f"{m.group(1)} 1, {m.group(2)}")
        if result:
            return result
    return None


def extract_articles(soup):
    """Extract paper entries from the transformer-circuits.pub index page."""
    articles = []
    seen_links = set()

    # Strategy 1: look for heading tags (h2–h4) that directly contain a paper link
    for tag_name in ("h2", "h3", "h4"):
        for heading in soup.find_all(tag_name):
            link_tag = heading.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag.get("href", "")
            if not _looks_like_paper_url(href):
                continue
            abs_link = _make_absolute(href)
            if not abs_link or abs_link in seen_links:
                continue

            title = link_tag.get_text(strip=True) or heading.get_text(strip=True)
            if not title:
                continue

            # Try to grab date and description from sibling/following elements
            date = None
            description = title
            # Walk through the next few siblings looking for date/author text
            context_texts = []
            for sib in heading.find_next_siblings():
                sib_tag = sib.name if hasattr(sib, "name") else None
                # Stop at the next heading
                if sib_tag in ("h2", "h3", "h4"):
                    break
                text = sib.get_text(separator=" ", strip=True)
                if text:
                    context_texts.append(text)
                # Limit how far we look ahead
                if len(context_texts) >= 4:
                    break

            if context_texts:
                description = context_texts[0]
                combined = " ".join(context_texts)
                date = _extract_date_from_text(combined)

            if date is None:
                date = stable_fallback_date(abs_link)

            article = {
                "title": title,
                "link": abs_link,
                "description": description,
                "date": date,
            }
            if validate_article(article, require_date=False):
                articles.append(article)
                seen_links.add(abs_link)

    if articles:
        logger.info(f"Strategy 1 found {len(articles)} articles via headings")
        return articles

    # Strategy 2: find any <a> tag whose href looks like a paper URL
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        if not _looks_like_paper_url(href):
            continue
        abs_link = _make_absolute(href)
        if not abs_link or abs_link in seen_links:
            continue

        title = a_tag.get_text(strip=True)
        if not title:
            continue

        # Use parent element text for date/description context
        parent_text = ""
        parent = a_tag.parent
        if parent:
            parent_text = parent.get_text(separator=" ", strip=True)

        date = _extract_date_from_text(parent_text) or stable_fallback_date(abs_link)
        description = parent_text or title

        article = {
            "title": title,
            "link": abs_link,
            "description": description,
            "date": date,
        }
        if validate_article(article, require_date=False):
            articles.append(article)
            seen_links.add(abs_link)

    logger.info(f"Strategy 2 found {len(articles)} articles via plain links")
    return articles


def parse_index_html(html_content):
    """Parse the index HTML and return a list of article dicts."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        articles = extract_articles(soup)
        return articles
    except Exception as e:
        logger.error(f"Error parsing HTML content: {str(e)}")
        raise


def main(feed_name="transformer_circuits"):
    """Main function to generate RSS feed for transformer-circuits.pub."""
    try:
        logger.info(f"Fetching index page from {INDEX_URL}")
        html_content = fetch_content(INDEX_URL)

        articles = parse_index_html(html_content)

        if not articles:
            logger.warning("No articles found on the index page")
            return False

        feed_config = {
            "title": "Transformer Circuits Thread",
            "description": "Research papers on the mathematical structure of transformer neural networks from transformer-circuits.pub",
            "link": BASE_URL,
            "language": "en",
            "author": {"name": "Transformer Circuits Authors"},
            "subtitle": "Interpretability research on transformer circuits",
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
