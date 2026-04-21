import json
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

BASE_URL = "https://nousresearch.com"
BLOG_URL = f"{BASE_URL}/blog"
MIN_SCRIPT_LENGTH = 50
MIN_EMBEDDED_TITLE_LENGTH = 5


def _make_absolute(href):
    """Convert a relative URL to an absolute one."""
    if not href:
        return None
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def extract_articles_from_json_ld(soup):
    """Extract articles from JSON-LD structured data."""
    articles = []
    article_types = {
        "Article",
        "BlogPosting",
        "NewsArticle",
        "ScholarlyArticle",
        "TechArticle",
    }

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]

            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("@type") not in article_types:
                    continue

                title = item.get("headline") or item.get("name")
                link = item.get("url") or (
                    item.get("mainEntityOfPage", {}).get("@id")
                    if isinstance(item.get("mainEntityOfPage"), dict)
                    else None
                )
                description = item.get("description") or title
                date_str = item.get("datePublished") or item.get("dateCreated")

                if not link or not link.startswith("http"):
                    continue

                date = parse_date(date_str) if date_str else stable_fallback_date(link)
                article = {
                    "title": title,
                    "link": link,
                    "description": description,
                    "date": date,
                }
                if validate_article(article, require_date=False):
                    articles.append(article)
        except (json.JSONDecodeError, AttributeError):
            continue

    return articles


def _parse_article_dict(item):
    """Parse a single article dict into an article object."""
    if not isinstance(item, dict):
        return None

    title = item.get("title") or item.get("name") or item.get("headline")
    if not title:
        return None

    link = item.get("url") or item.get("link") or item.get("href")
    if not link:
        slug = item.get("slug")
        if isinstance(slug, dict):
            slug = slug.get("current") or slug.get("_current")
        if isinstance(slug, str) and slug:
            link = f"{BLOG_URL}/{slug.lstrip('/')}"
    if not link:
        return None

    link = _make_absolute(link)
    if not link:
        return None

    description = (
        item.get("description")
        or item.get("summary")
        or item.get("excerpt")
        or item.get("subtitle")
        or title
    )
    date_str = (
        item.get("date")
        or item.get("publishedAt")
        or item.get("publishedOn")
        or item.get("published_at")
        or item.get("createdAt")
        or item.get("datePublished")
        or item.get("dateCreated")
        or item.get("_createdAt")
        or item.get("_updatedAt")
        or item.get("publish_date")
        or item.get("postDate")
        or item.get("created")
        or item.get("published")
    )
    date = parse_date(date_str) if date_str else stable_fallback_date(link)

    article = {
        "title": title,
        "link": link,
        "description": description,
        "date": date,
    }
    return article if validate_article(article, require_date=False) else None


def _search_nested_for_articles(data, depth=0):
    """Recursively search nested dicts/lists for article collections."""
    if depth > 5:
        return []

    if isinstance(data, list) and data:
        parsed = [_parse_article_dict(item) for item in data if isinstance(item, dict)]
        valid = [a for a in parsed if a]
        if len(valid) >= 2:
            return valid

        for item in data:
            found = _search_nested_for_articles(item, depth + 1)
            if found:
                return found

    elif isinstance(data, dict):
        for key in (
            "posts",
            "articles",
            "blog",
            "blogPosts",
            "items",
            "results",
            "data",
            "nodes",
            "edges",
            "entries",
        ):
            if key in data:
                found = _search_nested_for_articles(data[key], depth + 1)
                if found:
                    return found

        for value in data.values():
            if isinstance(value, (dict, list)):
                found = _search_nested_for_articles(value, depth + 1)
                if found:
                    return found

    return []


def extract_articles_from_next_data(soup):
    """Extract articles from Next.js __NEXT_DATA__ script tag."""
    next_data_script = soup.find("script", id="__NEXT_DATA__")
    if not next_data_script or not next_data_script.string:
        return []

    try:
        data = json.loads(next_data_script.string)
        page_props = data.get("props", {}).get("pageProps", {})
        return _search_nested_for_articles(page_props)
    except (json.JSONDecodeError, AttributeError):
        return []


def extract_articles_from_script_tags(soup):
    """Extract articles from inline script tags containing JSON data."""
    for script in soup.find_all("script"):
        content = script.string or ""
        if not content or len(content) < MIN_SCRIPT_LENGTH:
            continue
        if script.get("type") == "application/ld+json":
            continue

        patterns = [
            rf'"title"\s*:\s*"[^"]{{{MIN_EMBEDDED_TITLE_LENGTH},}}"',
            rf'"headline"\s*:\s*"[^"]{{{MIN_EMBEDDED_TITLE_LENGTH},}}"',
        ]
        if not any(re.search(pattern, content) for pattern in patterns):
            continue

        try:
            data = json.loads(content)
            found = _search_nested_for_articles(data)
            if found:
                return found
        except (json.JSONDecodeError, ValueError):
            pass

    return []


def extract_articles_from_html(soup):
    """Extract articles using common HTML patterns for blog pages."""
    articles = []
    seen_links = set()

    candidate_groups = [
        soup.find_all("article"),
        soup.find_all("a", href=re.compile(r"^/blog/.+")),
        soup.select(
            ".post-card, .blog-card, .article-card, .blog-post, "
            ".post-item, .article-item, .card, "
            "[class*='PostCard'], [class*='ArticleCard'], [class*='BlogCard'], "
            "[class*='post-card'], [class*='article-card'], [class*='blog-card']"
        ),
    ]

    for items in candidate_groups:
        if not items:
            continue

        for item in items:
            try:
                link_elem = item if item.name == "a" else item.find("a")
                if not link_elem:
                    continue

                href = link_elem.get("href", "")
                if not href or href in ("#", "/"):
                    continue

                link = _make_absolute(href)
                if not link or not link.startswith("http"):
                    continue
                if link in seen_links:
                    continue

                seen_links.add(link)
                title_elem = item.find(["h1", "h2", "h3", "h4", "h5"])
                title = (
                    title_elem.get_text(strip=True)
                    if title_elem
                    else link_elem.get_text(strip=True)
                )
                title = " ".join(title.split())
                if not title or len(title) < 3:
                    continue

                container = (
                    item.find_parent("li") or item.parent
                    if item.name == "a"
                    else item
                )

                date_text = None
                time_elem = container.find("time") if container else None
                if time_elem:
                    date_text = time_elem.get("datetime") or time_elem.get_text(
                        strip=True
                    )
                if not date_text:
                    date_elem = (
                        container.select_one("[class*='date'], [class*='Date']")
                        if container
                        else None
                    )
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)

                date = parse_date(date_text) if date_text else stable_fallback_date(link)

                desc_elem = (
                    (
                        container.find("p")
                        or container.select_one(
                            "[class*='description'], [class*='excerpt'], [class*='summary']"
                        )
                    )
                    if container
                    else None
                )
                description = desc_elem.get_text(strip=True) if desc_elem else title

                article = {
                    "title": title,
                    "link": link,
                    "description": description,
                    "date": date,
                }
                if validate_article(article, require_date=False):
                    articles.append(article)
            except Exception as e:
                logger.warning(f"Error parsing article element: {str(e)}")
                continue

        if articles:
            logger.info(
                f"Extracted {len(articles)} articles using HTML selector group"
            )
            break

    return articles


def parse_nousresearch_html(html_content):
    """Parse Nous Research blog HTML and extract articles."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        articles = extract_articles_from_json_ld(soup)
        if articles:
            logger.info(f"Extracted {len(articles)} articles from JSON-LD data")
            return articles

        articles = extract_articles_from_next_data(soup)
        if articles:
            logger.info(f"Extracted {len(articles)} articles from __NEXT_DATA__")
            return articles

        articles = extract_articles_from_script_tags(soup)
        if articles:
            logger.info(f"Extracted {len(articles)} articles from script tags")
            return articles

        articles = extract_articles_from_html(soup)
        if articles:
            logger.info(f"Extracted {len(articles)} articles from HTML patterns")
            return articles

        logger.warning("No articles found using any parsing strategy")
        return []

    except Exception as e:
        logger.error(f"Error parsing HTML content: {str(e)}")
        raise


def main(feed_name="nousresearch"):
    """Main function to generate RSS feed from Nous Research's blog page."""
    try:
        logger.info(f"Fetching content from {BLOG_URL}")
        html_content = fetch_content(BLOG_URL)

        articles = parse_nousresearch_html(html_content)
        if not articles:
            logger.warning("No articles found on the Nous Research blog")
            return False

        feed_config = {
            "title": "Nous Research Blog",
            "description": "Latest posts and updates from Nous Research",
            "link": BLOG_URL,
            "language": "en",
            "author": {"name": "Nous Research"},
            "subtitle": "Blog posts from Nous Research",
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
