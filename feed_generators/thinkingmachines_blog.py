from bs4 import BeautifulSoup
from utils import (
    extract_title,
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
                "description": f"{title} by {author_text}",
                "pub_date": pub_date,
                "author": author_text,
            }

            # Validate article
            if validate_article(article, require_date=False):
                articles.append(article)
                logger.info(f"Parsed: {title} ({date_text}) by {author_text}")
            else:
                logger.warning(f"Article failed validation: {link}")

        except Exception as e:
            logger.warning(f"Failed to parse article: {str(e)}")
            continue

    # Sort by date (newest first)
    articles.sort(key=lambda x: x["pub_date"], reverse=False)

    logger.info(f"Successfully parsed {len(articles)} articles")
    return articles


def parse_html(html_content):
    """Parse HTML content."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        return extract_articles(soup)
    except Exception as e:
        logger.error(f"Error parsing HTML content: {str(e)}")
        raise


def generate_thinkingmachines_feed(articles, feed_name="thinkingmachines"):
    """Generate RSS feed using feedgen."""
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
    return generate_rss_feed(articles, feed_config)


def save_thinkingmachines_feed(feed_generator, feed_name="thinkingmachines"):
    """Save feed to XML file."""
    feed_config = {
        "feed_name": feed_name,
        "filename_format": "feed_{feed_name}.xml",
        "pretty": True,
    }
    return save_rss_feed(feed_generator, feed_config)


def main(feed_name="thinkingmachines"):
    """Main entry point."""
    try:
        # Fetch from website
        logger.info("Fetching content from website")
        html_content = fetch_content("https://thinkingmachines.ai/blog/")

        # Parse articles
        articles = parse_html(html_content)

        # Generate RSS feed
        feed = generate_thinkingmachines_feed(articles, feed_name)

        # Save feed to file
        _output_file = save_thinkingmachines_feed(feed, feed_name)

        logger.info(f"Successfully generated RSS feed with {len(articles)} articles")
        return True

    except Exception as e:
        logger.error(f"Failed to generate RSS feed: {str(e)}")
        return False


if __name__ == "__main__":
    main()
