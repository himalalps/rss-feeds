from bs4 import BeautifulSoup
from utils import (
    extract_date,
    extract_title,
    fetch_content,
    generate_rss_feed,
    save_rss_feed,
    setup_logging,
    validate_article,
)

# Set up logging
logger = setup_logging(__name__)


def parse_research_html(html_content):
    """Parse the research HTML content and extract article information."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        articles = []
        seen_links = set()

        # Look for research article links using flexible selector
        research_links = soup.select("a[href*='/research/']")
        logger.info(f"Found {len(research_links)} potential research article links")

        for link in research_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue

                # Skip the main research page
                if href == "/research" or href.endswith("/research/"):
                    continue

                # Construct full URL
                if href.startswith("https://"):
                    full_url = href
                elif href.startswith("/"):
                    full_url = "https://www.anthropic.com" + href
                else:
                    continue

                # Skip duplicates
                if full_url in seen_links:
                    continue
                seen_links.add(full_url)

                # Extract title
                title = extract_title(link)
                if not title:
                    logger.debug(f"Could not extract title for link: {full_url}")
                    continue

                # Extract date (can be None for research articles)
                date = extract_date(link)
                if date:
                    logger.info(f"Found article: {title} - {date}")
                else:
                    logger.info(f"Found article (no date): {title}")

                # Determine category from URL
                category = "Research"
                if "/news/" in href:
                    category = "News"

                article = {
                    "title": title,
                    "link": full_url,
                    "date": date,  # Can be None
                    "category": category,
                    "description": title,
                }

                # Validate article - research articles may not have dates
                if validate_article(article, require_date=True):
                    articles.append(article)
                else:
                    logger.debug(f"Article failed validation: {full_url}")

            except Exception as e:
                logger.warning(f"Error parsing research link: {str(e)}")
                continue

        logger.info(f"Successfully parsed {len(articles)} unique research articles")
        articles.sort(key=lambda x: x["date"] or "", reverse=True)
        return articles

    except Exception as e:
        logger.error(f"Error parsing HTML content: {str(e)}")
        raise


def main(feed_name="anthropic_research"):
    """Main function to generate RSS feed from Anthropic's research page."""
    try:
        # Fetch research content using requests
        html_content = fetch_content("https://www.anthropic.com/research")

        # Parse articles from HTML
        articles = parse_research_html(html_content)

        if not articles:
            logger.warning("No articles found. Please check the HTML structure.")
            return False

        feed_config = {
            "title": "Anthropic Research",
            "description": "Latest research papers and updates from Anthropic",
            "link": "https://www.anthropic.com/research",
            "language": "en",
            "author": {"name": "Anthropic Research Team"},
            "logo": "https://www.anthropic.com/images/icons/apple-touch-icon.png",
            "subtitle": "Latest research from Anthropic",
            "sort_reverse": False,
            "date_field": "date",
        }
        feed = generate_rss_feed(articles, feed_config)

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
