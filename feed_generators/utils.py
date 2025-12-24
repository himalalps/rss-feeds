import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import requests


def setup_logging(name):
    """Set up logging for the feed generator."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    return logging.getLogger(name)


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


def ensure_feeds_directory():
    """Ensure the feeds directory exists."""
    feeds_dir = get_project_root() / "feeds"
    feeds_dir.mkdir(exist_ok=True)
    return feeds_dir


def fetch_content(url, user_agent=None, timeout=10):
    """Fetch content from website with error handling."""
    try:
        headers = {
            "User-Agent": user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger = setup_logging(__name__)
        logger.error(f"Error fetching content from {url}: {str(e)}")
        raise


def stable_fallback_date(identifier):
    """Generate a stable date from a URL or title hash."""
    hash_val = abs(hash(identifier)) % 730
    epoch = datetime(2023, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    return epoch + timedelta(days=hash_val)


def parse_date(date_text):
    """Parse dates with multiple format support."""
    if not date_text:
        return None

    date_text = date_text.strip()
    current_year = datetime.now().year

    # List of date formats to try
    date_formats = [
        "%b %d",  # "Nov 7", "Oct 29"
        "%B %d",  # "November 7", "October 29"
        "%b %d, %Y",  # "Nov 7, 2025"
        "%B %d, %Y",  # "November 7, 2025"
        "%Y-%m-%d",  # "2025-11-07"
        "%m/%d/%Y",  # "11/07/2025"
        "%d %b %Y",  # "07 Nov 2025"
        "%d %B %Y",  # "07 November 2025"
        "%b %d %Y",  # "Nov 07 2025"
        "%B %d %Y",  # "November 07 2025"
    ]

    for date_format in date_formats:
        try:
            date = datetime.strptime(date_text, date_format)
            # If the format doesn't include year, add current year
            if "%Y" not in date_format:
                date = date.replace(year=current_year)
            return date.replace(tzinfo=pytz.UTC)
        except ValueError:
            continue

    # If all formats fail, log warning and return None
    logger = setup_logging(__name__)
    logger.warning(f"Could not parse date: {date_text}")
    return None


def extract_date(card):
    """Extract date using multiple fallback selectors and formats."""
    selectors = [
        "p.detail-m",  # Current format on listing page
        ".detail-m",
        "time",
        "[class*='timestamp']",
        "[class*='date']",
        ".PostDetail_post-timestamp__TBJ0Z",
        ".text-label",
    ]

    logger = setup_logging(__name__)

    # Look for date in the card and its parents
    elements_to_check = [card]
    if hasattr(card, "parent") and card.parent:
        elements_to_check.append(card.parent)
        if card.parent.parent:
            elements_to_check.append(card.parent.parent)

    for element in elements_to_check:
        for selector in selectors:
            date_elem = element.select_one(selector)
            if date_elem:
                date_text = date_elem.text.strip()
                date = parse_date(date_text)
                if date:
                    return date

    return None


def extract_title(card):
    """Extract title using multiple fallback selectors."""
    selectors = [
        "h3",
        "h2",
        "h1",
        ".Card_headline__reaoT",
        "h3[class*='headline']",
        "h2[class*='headline']",
        "h3[class*='title']",
        "h2[class*='title']",
    ]

    for selector in selectors:
        elem = card.select_one(selector)
        if elem and elem.text.strip():
            title = elem.text.strip()
            # Clean up whitespace
            title = " ".join(title.split())
            if len(title) >= 5:
                return title

    # Try using link text as last resort
    if hasattr(card, "text"):
        text = card.text.strip()
        text = " ".join(text.split())
        if len(text) >= 5:
            return text

    return None


def validate_article(article, require_date=True):
    """Validate article has required fields."""
    if not article.get("title") or len(article["title"]) < 5:
        return False
    if not article.get("link") or not article["link"].startswith("http"):
        return False
    if require_date and not article.get("date"):
        return False
    return True


def generate_rss_feed(articles, feed_config):
    """Generate RSS feed from articles with flexible configuration.

    Args:
        articles: List of article dictionaries with keys: title, link, description, date/pub_date,
                  category (optional), author (optional)
        feed_config: Dictionary with feed configuration:
            - title: Feed title
            - description: Feed description
            - link: Feed link
            - language: Feed language
            - author (optional): Author information
            - logo (optional): Logo URL
            - subtitle (optional): Feed subtitle
            - sort_reverse (optional): Whether to sort articles in reverse order (default: True)
            - date_field (optional): Field name for date (default: "date", falls back to "pub_date")
    """
    from feedgen.feed import FeedGenerator

    logger = setup_logging(__name__)

    try:
        fg = FeedGenerator()

        # Set basic feed info
        fg.title(feed_config["title"])
        fg.description(feed_config["description"])
        fg.link(href=feed_config["link"])
        fg.language(feed_config.get("language", "en"))

        # Set optional feed metadata
        if "author" in feed_config:
            fg.author(feed_config["author"])
        if "logo" in feed_config:
            fg.logo(feed_config["logo"])
        if "subtitle" in feed_config:
            fg.subtitle(feed_config["subtitle"])

        # Handle article sorting
        date_field = feed_config.get("date_field", "date")

        # Separate articles with and without dates if needed
        articles_with_date = [
            a for a in articles if a.get(date_field) or a.get("pub_date")
        ]
        articles_without_date = [
            a for a in articles if not a.get(date_field) and not a.get("pub_date")
        ]

        # Get the actual date field present in the articles
        actual_date_field = (
            date_field
            if articles_with_date and date_field in articles_with_date[0]
            else "pub_date"
        )

        # Sort articles with dates
        sort_reverse = feed_config.get("sort_reverse", True)
        articles_with_date.sort(
            key=lambda x: x[actual_date_field], reverse=sort_reverse
        )

        # Combine sorted articles with those without dates
        sorted_articles = articles_with_date + articles_without_date

        # Add entries to feed
        for article in sorted_articles:
            fe = fg.add_entry()
            fe.title(article["title"])
            fe.description(article["description"])
            fe.link(href=article["link"])
            fe.id(article["link"])

            # Add date if available
            pub_date = article.get(date_field) or article.get("pub_date")
            if pub_date:
                fe.published(pub_date)

            # Add category if available
            if "category" in article:
                fe.category(term=article["category"])

            # Add author if available
            if "author" in article:
                fe.author({"name": article["author"]})

        logger.info("Successfully generated RSS feed")
        return fg

    except Exception as e:
        logger.error(f"Error generating RSS feed: {str(e)}")
        raise


def save_rss_feed(feed_generator, feed_config):
    """Save RSS feed to file with flexible configuration.

    Args:
        feed_generator: FeedGenerator object
        feed_config: Dictionary with save configuration:
            - feed_name: Name of the feed (used in filename)
            - filename_format: Format string for filename (default: "feed_{feed_name}.xml")
            - pretty: Whether to format the XML nicely (default: True)
    """
    logger = setup_logging(__name__)

    try:
        # Ensure feeds directory exists and get its path
        feeds_dir = ensure_feeds_directory()

        # Create the output file path
        feed_name = feed_config["feed_name"]
        filename_format = feed_config.get("filename_format", "feed_{feed_name}.xml")
        output_filename = feeds_dir / filename_format.format(feed_name=feed_name)

        # Save the feed
        pretty = feed_config.get("pretty", True)
        feed_generator.rss_file(str(output_filename), pretty=pretty)

        logger.info(f"Successfully saved RSS feed to {output_filename}")
        return output_filename

    except Exception as e:
        logger.error(f"Error saving RSS feed: {str(e)}")
        raise
