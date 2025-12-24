import re

from bs4 import BeautifulSoup
from utils import (
    fetch_content,
    generate_rss_feed,
    parse_date,
    save_rss_feed,
    setup_logging,
    validate_article,
)

# Set up logging
logger = setup_logging(__name__)


def extract_articles(script_content):
    """Extract article information from the Next.js script content."""
    articles = []
    pattern = r'\\"publishedOn\\":\\"([^"]+?)\\",\\"slug\\":\{[^}]*?\\"current\\":\\"([^"]+?)\\"'
    matches = re.findall(pattern, script_content)

    logger.info(f"Found {len(matches)} articles from JSON data")

    for published_date, slug in matches:
        try:
            # Construct the full URL from the slug
            link = f"https://www.anthropic.com/research/{slug}"

            # Find the article object containing this slug to get title and summary
            # Search for the section containing this slug
            slug_pos = script_content.find(f'\\"current\\":\\"{slug}\\"')
            if slug_pos == -1:
                continue

            # Search forward from slug position to find the title and summary
            # The structure is: ...publishedOn, slug, ...other fields..., summary, title}
            search_section = script_content[slug_pos : slug_pos + 2000]

            # Extract title and summary (they appear AFTER the slug in the data)
            # Use negative lookbehind to handle escaped quotes correctly
            title_match = re.search(r'\\"title\\":\\"(.*?)(?<!\\)\\"', search_section)
            title = (
                title_match.group(1) if title_match else slug.replace("-", " ").title()
            )
            # Unescape the title using re.sub to handle all escaped characters
            title = re.sub(r"\\(.)", r"\1", title) if title else title

            # Extract summary/description
            summary_match = re.search(
                r'\\"summary\\":\\"(.*?)(?<!\\)\\"', search_section
            )
            description = summary_match.group(1) if summary_match else title
            # Unescape the description
            description = (
                re.sub(r"\\(.)", r"\1", description) if description else description
            )

            # Parse the date
            date = parse_date(published_date)

            # Parse category
            category_match = re.search(r'\\"label\\":\\"(.*?)(?<!\\)\\"', search_section)
            category = category_match.group(1) if category_match else "Research"

            article = {
                "title": title,
                "link": link,
                "description": description if description else title,
                "date": date,
                "category": category,
            }

            # Validate article - research articles may not have dates
            if validate_article(article, require_date=True):
                articles.append(article)

        except Exception as e:
            logger.warning(f"Error parsing research link: {str(e)}")
            continue

    logger.info(f"Successfully parsed {len(articles)} unique research articles")
    # articles.sort(key=lambda x: x["date"] or "", reverse=True)
    return articles


def parse_research_html(html_content):
    """Parse the research HTML content and extract article information."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        # Find the Next.js script tag containing article data
        script_tag = None
        for script in soup.find_all("script"):
            if script.string and "publishedOn" in script.string:
                script_tag = script
                break

        if not script_tag:
            logger.error(
                "Could not find Next.js data script containing article information"
            )
            return []

        script_content = script_tag.string
        articles = extract_articles(script_content)
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
