import re
from datetime import datetime

import pytz
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


def parse_engineering_html(html_content):
    """Parse the engineering HTML content and extract article information from embedded JSON."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        articles = []

        # Find the Next.js script tag containing article data
        script_tag = None
        for script in soup.find_all("script"):
            if (
                script.string
                and "publishedOn" in script.string
                and "engineeringArticle" in script.string
            ):
                script_tag = script
                break

        if not script_tag:
            logger.error(
                "Could not find Next.js data script containing article information"
            )
            return []

        script_content = script_tag.string

        # Extract article data from the escaped JSON in the Next.js script
        # Pattern matches: publishedOn, slug, title, and summary fields
        

        pattern = r'\\"publishedOn\\":\\"([^"]+?)\\",\\"slug\\":\{[^}]*?\\"current\\":\\"([^"]+?)\\"'
        matches = re.findall(pattern, script_content)

        logger.info(f"Found {len(matches)} articles from JSON data")

        for published_date, slug in matches:
            try:
                # Construct the full URL from the slug
                link = f"https://www.anthropic.com/engineering/{slug}"

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
                title_match = re.search(
                    r'\\"title\\":\\"(.*?)(?<!\\)\\"', search_section
                )
                title = (
                    title_match.group(1)
                    if title_match
                    else slug.replace("-", " ").title()
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
                date = datetime.strptime(published_date, "%Y-%m-%d")
                date = date.replace(hour=0, minute=0, second=0, tzinfo=pytz.UTC)

                article = {
                    "title": title,
                    "link": link,
                    "description": description if description else title,
                    "date": date,
                    "category": "Engineering",
                }

                if validate_article(article):
                    articles.append(article)
                    logger.info(f"Found article: {title} ({published_date})")

            except Exception as e:
                logger.warning(f"Error parsing article {slug}: {str(e)}")
                continue

        logger.info(f"Successfully parsed {len(articles)} articles from JSON data")
        articles.sort(key=lambda x: x["date"], reverse=True)
        return articles

    except Exception as e:
        logger.error(f"Error parsing HTML content: {str(e)}")
        raise


def main(feed_name="anthropic_engineering"):
    """Main function to generate RSS feed from Anthropic's engineering page."""
    try:
        # Fetch engineering content
        html_content = fetch_content("https://www.anthropic.com/engineering")

        # Parse articles from HTML
        articles = parse_engineering_html(html_content)

        if not articles:
            logger.warning("No articles found on the engineering page")
            return False

        # Generate RSS feed
        feed_config = {
            "title": "Anthropic Engineering Blog",
            "description": "Latest engineering articles and insights from Anthropic's engineering team",
            "link": "https://www.anthropic.com/engineering",
            "language": "en",
            "author": {"name": "Anthropic Engineering Team"},
            "logo": "https://www.anthropic.com/images/icons/apple-touch-icon.png",
            "subtitle": "Inside the team building reliable AI systems",
            "sort_reverse": False,
            "date_field": "date",
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
