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


def extract_title(card):
    """Extract title using multiple fallback selectors."""
    selectors = ["div[class='post-title']"]

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


def extract_articles(soup):
    """Extract article information from HTML."""
    articles = []
    seen_links = set()

    # Find all post items
    post_items = soup.select("li a.post-item-link")
    logger.info(f"Found {len(post_items)} potential articles")

    for item in post_items:
        try:
            # Extract link
            href = item.get("href", "")
            if not href:
                continue

            # Build full URL
            link = (
                f"https://thinkingmachines.ai{href}" if href.startswith("/") else href
            )

            # Skip duplicates
            if link in seen_links:
                continue
            seen_links.add(link)

            # Extract date from time element
            date_elem = item.select_one("time.desktop-time")
            date_text = date_elem.get_text(strip=True) if date_elem else None
            pub_date = parse_date(date_text) or stable_fallback_date(link)

            # Extract title using utils function
            title = extract_title(item) or "Untitled"

            # Extract author from author-date div
            author_elem = item.select_one("div.author-date")
            author_text = ""
            if author_elem:
                # Get the text before the mobile date separator
                author_text = author_elem.get_text(strip=True)
                # Remove the date part (after the separator)
                if "·" in author_text:
                    author_text = author_text.split("·")[0].strip()

            if not author_text:
                author_text = "Thinking Machines Lab"

            # Create article object
            article = {
                "title": title,
                "link": link,
                "description": f"by {author_text}",
                "pub_date": pub_date,
                "author": author_text,
            }

            # Validate article
            if validate_article(article, require_date=False):
                articles.append(article)

        except Exception as e:
            logger.warning(f"Failed to parse article: {str(e)}")
            continue

    logger.info(f"Successfully parsed {len(articles)} articles")
    return articles


def parse_thinkingmachines_html(html_content):
    """Parse HTML content."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        return extract_articles(soup)
    except Exception as e:
        logger.error(f"Error parsing HTML content: {str(e)}")
        raise


def main(feed_name="thinkingmachines"):
    """Main entry point."""
    try:
        # Fetch from website
        logger.info("Fetching content from website")
        html_content = fetch_content("https://thinkingmachines.ai/blog/")

        # Parse articles
        articles = parse_thinkingmachines_html(html_content)

        if not articles:
            logger.warning("No articles found on the Thinking Machines blog")
            return False

        # Generate RSS feed
        feed_config = {
            "title": "Thinking Machines Lab - Connectionism",
            "description": "Research blog by Thinking Machines Lab - Shared science and news from the team",
            "link": "https://thinkingmachines.ai/blog/",
            "language": "en",
            "author": {"name": "Thinking Machines Lab"},
            "subtitle": "Shared science and news from the team",
            "sort_reverse": False,
            "date_field": "pub_date",
        }
        feed = generate_rss_feed(articles, feed_config)

        # Save RSS feed
        feed_config = {
            "feed_name": feed_name,
            "pretty": True,
        }
        save_rss_feed(feed, feed_config)

        logger.info(f"Successfully generated RSS feed with {len(articles)} articles")
        return True

    except Exception as e:
        logger.error(f"Failed to generate RSS feed: {str(e)}")
        return False


if __name__ == "__main__":
    main()
