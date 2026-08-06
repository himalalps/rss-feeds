import shutil
import subprocess
import time
from datetime import datetime

import pytz
import requests
from utils import generate_rss_feed, save_rss_feed, setup_logging, validate_article

logger = setup_logging(__name__)

RESEARCH_URL = "https://hy.tencent.ai/research?page=1"
CHROMEDRIVER_PORT = 9515
DATE_FORMAT = "%b %d, %Y"


class ChromeDriverClient:
    """Small WebDriver client using the ChromeDriver bundled on GitHub runners."""

    def __init__(self, port=CHROMEDRIVER_PORT):
        self.base_url = f"http://127.0.0.1:{port}"
        self.session_id = None
        executable = shutil.which("chromedriver")
        if not executable:
            raise RuntimeError("chromedriver is required to render Tencent Hy")

        self.process = subprocess.Popen(
            [executable, f"--port={port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self._wait_for_driver()
            response = self._request(
                "POST",
                "/session",
                {
                    "capabilities": {
                        "alwaysMatch": {
                            "browserName": "chrome",
                            "goog:chromeOptions": {
                                "args": [
                                    "--headless=new",
                                    "--no-sandbox",
                                    "--disable-dev-shm-usage",
                                    "--window-size=1440,1200",
                                ]
                            },
                        }
                    }
                },
            )
            self.session_id = response["sessionId"]
        except Exception:
            self.process.terminate()
            self.process.wait(timeout=5)
            raise

    def _wait_for_driver(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if requests.get(f"{self.base_url}/status", timeout=1).ok:
                    return
            except requests.RequestException:
                time.sleep(0.2)
        raise RuntimeError("chromedriver did not start")

    def _request(self, method, path, payload=None):
        response = requests.request(
            method, f"{self.base_url}{path}", json=payload, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        value = data.get("value", data)
        if isinstance(value, dict) and value.get("error"):
            raise RuntimeError(value.get("message", value["error"]))
        return value

    def navigate(self, url):
        self._request("POST", f"/session/{self.session_id}/url", {"url": url})

    def current_url(self):
        return self._request("GET", f"/session/{self.session_id}/url")

    def execute(self, script, args=None):
        return self._request(
            "POST",
            f"/session/{self.session_id}/execute/sync",
            {"script": script, "args": args or []},
        )

    def close(self):
        if self.session_id:
            try:
                self._request("DELETE", f"/session/{self.session_id}")
            except (requests.RequestException, RuntimeError):
                pass
            self.session_id = None
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def wait_until(condition, timeout=20, interval=0.25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval)
    raise RuntimeError("Timed out waiting for Tencent Hy to render")


def parse_row_text(text):
    """Parse a rendered research row into date, title, and author text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(f"Unexpected research row: {text!r}")
    date = datetime.strptime(lines[0], DATE_FORMAT).replace(tzinfo=pytz.UTC)
    author = " ".join(" ".join(lines[2:]).split())
    return {"date": date, "title": lines[1], "author": author}


def get_rows(driver):
    return driver.execute(
        """
        return Array.from(document.querySelectorAll('.research-list__row'))
          .map((row) => row.innerText);
        """
    )


def get_description(driver, title):
    paragraphs = driver.execute(
        """
        return Array.from(document.querySelectorAll('main p'))
          .map((node) => node.innerText.trim())
          .filter((text) => text.length > 30);
        """
    )
    return paragraphs[0] if paragraphs else title


def parse_research_page():
    """Render the research SPA and resolve each card's real detail URL."""
    articles = []
    seen_links = set()

    with ChromeDriverClient() as driver:
        driver.navigate(RESEARCH_URL)
        rows = wait_until(lambda: get_rows(driver))

        for index in range(len(rows)):
            if index:
                driver.navigate(RESEARCH_URL)
                rows = wait_until(lambda: get_rows(driver))

            article = parse_row_text(rows[index])
            listing_url = driver.current_url()
            driver.execute(
                """
                const rows = document.querySelectorAll('.research-list__row');
                if (!rows[arguments[0]]) throw new Error('Research row not found');
                rows[arguments[0]].click();
                """,
                [index],
            )
            link = wait_until(
                lambda: (
                    driver.current_url()
                    if driver.current_url() != listing_url
                    else None
                )
            )
            wait_until(
                lambda: driver.execute(
                    """
                    return document.querySelectorAll('.research-list__row').length === 0
                      && document.querySelector('main')?.innerText.length > 100;
                    """
                )
            )

            article["link"] = link
            article["description"] = get_description(driver, article["title"])
            if link not in seen_links and validate_article(article):
                articles.append(article)
                seen_links.add(link)

    logger.info(f"Successfully parsed {len(articles)} Tencent Hy research posts")
    return articles


def main(feed_name="tencent_hy_research"):
    """Generate the RSS feed for Tencent Hy Research."""
    try:
        articles = parse_research_page()
        if not articles:
            logger.warning("No research posts found on Tencent Hy")
            return False

        feed = generate_rss_feed(
            articles,
            {
                "title": "Tencent Hy Research",
                "description": "Latest research publications from Tencent Hy",
                "link": RESEARCH_URL,
                "language": "en",
                "author": {"name": "Tencent Hy"},
                "subtitle": "Research publications from Tencent Hy",
                "sort_reverse": False,
                "date_field": "date",
            },
        )
        save_rss_feed(feed, {"feed_name": feed_name, "pretty": True})
        logger.info(f"Successfully generated RSS feed with {len(articles)} articles")
        return True
    except Exception as error:
        logger.error(f"Failed to generate RSS feed: {error}")
        return False


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
