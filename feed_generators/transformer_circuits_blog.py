import json
import re
from datetime import datetime

import pytz
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
    # Paper URLs contain a 4-digit year segment (1900–2099, with or without a leading slash)
    return bool(re.search(r"(?:^|/)(?:19|20)\d{2}/", href))


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


def _extract_date_for_article_in_text(text, title):
    """Find the section-header date that precedes *title* inside a full-index text blob.

    When the parent element's text is the entire page index (e.g.
    "April 2026 Emotion Concepts … December 2025 Circuits Cross-Post …"),
    this locates the article title and returns the last 'Month YYYY' heading
    found before it, which is the month the paper was published.

    Returns a timezone-aware datetime, or None.
    """
    if not text or not title:
        return None
    pos = text.find(title[:40])
    if pos < 0:
        return None
    before = text[:pos]
    matches = list(re.finditer(r"\b([A-Z][a-z]+)\s+(\d{4})\b", before))
    if not matches:
        return None
    last = matches[-1]
    return parse_date(f"{last.group(1)} 1, {last.group(2)}")


_MAX_DESCRIPTION_LENGTH = 500


def _extract_description_for_article_in_text(text, title):
    """Extract the article's own short description from a full-index text blob.

    Looks for the text that follows *title* up to the next 'Month YYYY' section
    header, which is the article's abstract/description in the index.

    Returns a stripped string, or None.
    """
    if not text or not title:
        return None
    pos = text.find(title[:40])
    if pos == -1:
        return None
    after = text[pos + len(title):].lstrip()
    # Stop at the next section-header date pattern
    next_date = re.search(r"\b[A-Z][a-z]+ \d{4}\b", after)
    snippet = after[: next_date.start()].strip() if next_date else after.strip()
    return snippet[:_MAX_DESCRIPTION_LENGTH] if snippet else None


_MONTH_NAME_TO_NUM = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _extract_year_month_from_url(url):
    """Derive a date from a transformer-circuits URL.

    URLs follow the pattern  /<year>/<slug>/...
    The slug sometimes encodes the month (e.g. 'september-update').
    Returns a timezone-aware datetime or None.
    """
    m = re.search(r"/(\d{4})/([^/]+)/", url)
    if not m:
        return None
    year = int(m.group(1))
    slug = m.group(2).lower()
    for name, num in _MONTH_NAME_TO_NUM.items():
        if name in slug:
            return datetime(year, num, 1, tzinfo=pytz.UTC)
    return datetime(year, 1, 1, tzinfo=pytz.UTC)


def fetch_article_date(url):
    """Fetch an individual article page and return its published date.

    Checks (in order):
      1. <meta> tags whose name/property contains 'publish' or equals 'date'
      2. JSON-LD datePublished / dateCreated / date fields
      3. <time> elements (datetime attribute or text content)

    Returns a timezone-aware datetime, or None if nothing is found.
    """
    if not url.startswith(BASE_URL):
        return None
    try:
        html = fetch_content(url)
        soup = BeautifulSoup(html, "html.parser")

        # 1. Meta tags
        for meta in soup.find_all("meta"):
            for attr in ("name", "property", "itemprop"):
                val = meta.get(attr, "").lower()
                if "publish" in val or val in ("date", "article:published_time"):
                    content = meta.get("content", "")
                    if content:
                        date = parse_date(content)
                        if date:
                            return date

        # 2. JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                for key in ("datePublished", "dateCreated", "date"):
                    if key in data:
                        date = parse_date(data[key])
                        if date:
                            return date
            except Exception:
                pass

        # 3. <time> elements
        for time_tag in soup.find_all("time"):
            dt = time_tag.get("datetime", "") or time_tag.get_text(strip=True)
            if dt:
                date = parse_date(dt)
                if date:
                    return date

        return None
    except Exception:
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

            # If still no date, check the nearest preceding h2 for a month header
            # (e.g. the index page groups articles under "April 2026", "December 2025" …)
            if date is None:
                for prev_sib in heading.find_previous_siblings():
                    prev_tag = prev_sib.name if hasattr(prev_sib, "name") else None
                    if prev_tag == "h2":
                        date = _extract_date_from_text(
                            prev_sib.get_text(separator=" ", strip=True)
                        )
                        break

            # Fall back to fetching the individual article page for its published date
            if date is None:
                date = fetch_article_date(abs_link)

            # Last resort: derive year (and month when encoded in URL) from the URL path
            if date is None:
                date = _extract_year_month_from_url(abs_link)

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

        # Use parent element text for description and date extraction.
        # When the parent is the full page index, it contains "Month YYYY" section
        # headers that reveal which month each paper was published.
        parent_text = ""
        parent = a_tag.parent
        if parent:
            parent_text = parent.get_text(separator=" ", strip=True)

        # Prefer fetching the article page for an accurate published date, then try
        # to find the date by locating the article title in the parent text (works
        # when the parent holds the full page index with "Month YYYY" headers), then
        # fall back to extracting year/month from the URL, then the stable fallback.
        date = (
            fetch_article_date(abs_link)
            or _extract_date_for_article_in_text(parent_text, title)
            or _extract_year_month_from_url(abs_link)
            or stable_fallback_date(abs_link)
        )

        # Use the article's own abstract extracted from the index text when available;
        # otherwise fall back to the full parent text or the title.
        description = (
            _extract_description_for_article_in_text(parent_text, title)
            or parent_text
            or title
        )

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
            "sort_reverse": True,
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
