import xml.etree.ElementTree as ET
from html import unescape
import re
from urllib.parse import urlparse

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

logger = setup_logging(__name__)

BASE_URL = "https://plink.anyfeeder.com/people-daily"


def _is_xml_feed(content):
    content = content.lstrip()
    return content.startswith("<?xml") or "<rss" in content[:500] or "<feed" in content[:500]


def _extract_from_xml_feed(content):
    articles = []
    root = ET.fromstring(content)
    seen_links = set()

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        raw_description = (item.findtext("description") or title).strip()
        description = _extract_plain_article_text(raw_description) or title
        date = parse_date(item.findtext("pubDate")) or stable_fallback_date(link or title)

        article = {"title": title, "link": link, "description": description, "date": date}
        if link and link not in seen_links and validate_article(article, require_date=False):
            articles.append(article)
            seen_links.add(link)

    # Atom support
    if not articles:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            link_elem = entry.find("atom:link", ns)
            link = (link_elem.get("href") if link_elem is not None else "") or ""
            description = (
                entry.findtext("atom:summary", default="", namespaces=ns)
                or title
            ).strip()
            description = _extract_plain_article_text(description) or title
            date_text = entry.findtext("atom:updated", default="", namespaces=ns)
            date = parse_date(date_text) or stable_fallback_date(link or title)

            article = {"title": title, "link": link, "description": description, "date": date}
            if link and link not in seen_links and validate_article(article, require_date=False):
                articles.append(article)
                seen_links.add(link)

    return articles


def _extract_plain_article_text(raw_description):
    if not raw_description:
        return ""

    decoded = unescape(raw_description)
    match = re.search(
        r"<!--\s*enpcontent\s*-->(.*?)<!--\s*/enpcontent\s*-->",
        decoded,
        flags=re.IGNORECASE | re.DOTALL,
    )
    content_html = match.group(1) if match else decoded

    soup = BeautifulSoup(content_html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if p]
    if paragraphs:
        return "\n".join(paragraphs)

    text = soup.get_text("\n", strip=True)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _extract_from_html(content):
    soup = BeautifulSoup(content, "html.parser")
    articles = []
    seen_links = set()
    source_host = urlparse(BASE_URL).netloc

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()
        if not href or href.startswith("#"):
            continue
        if href.startswith("/"):
            href = f"https://{source_host}{href}"
        if not href.startswith("http"):
            continue

        title = " ".join(a_tag.get_text(" ", strip=True).split())
        if len(title) < 5:
            continue

        parsed = urlparse(href)
        if parsed.netloc == source_host and parsed.path in ("", "/people-daily", "/people-daily/"):
            continue

        # Keep only short preview text and direct users to the original page.
        description = "摘要省略，请点击原页面链接阅读。"

        date_elem = (
            a_tag.find_parent().find("time")
            if a_tag.find_parent()
            else None
        )
        date_text = ""
        if date_elem:
            date_text = date_elem.get("datetime") or date_elem.get_text(strip=True)
        date = parse_date(date_text) or stable_fallback_date(href)

        article = {"title": title, "link": href, "description": description, "date": date}
        if href not in seen_links and validate_article(article, require_date=False):
            articles.append(article)
            seen_links.add(href)

    return articles


def parse_people_daily_content(content):
    try:
        if _is_xml_feed(content):
            return _extract_from_xml_feed(content)
        return _extract_from_html(content)
    except Exception as e:
        logger.error(f"Error parsing source content: {str(e)}")
        raise


def main(feed_name="people_daily"):
    try:
        logger.info(f"Fetching content from {BASE_URL}")
        content = fetch_content(BASE_URL)

        articles = parse_people_daily_content(content)
        if not articles:
            logger.warning("No articles found for People Daily")
            return False

        feed_config = {
            "title": "People Daily",
            "description": "People Daily",
            "link": BASE_URL,
            "language": "zh-cn",
            "author": {"name": "People Daily"},
            "subtitle": "基于原页面链接生成的 RSS 订阅",
            "sort_reverse": False,
            "date_field": "date",
        }
        feed = generate_rss_feed(articles, feed_config)

        save_config = {"feed_name": feed_name, "pretty": True}
        save_rss_feed(feed, save_config)

        logger.info(f"Successfully generated RSS feed with {len(articles)} articles")
        return True
    except Exception as e:
        logger.error(f"Failed to generate RSS feed: {str(e)}")
        return False


if __name__ == "__main__":
    main()
