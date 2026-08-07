import logging
import urllib.parse
import requests
from bs4 import BeautifulSoup
from retrieval.schemas import ContentRole, PathResource, ResourceType

log = logging.getLogger("lumina.web_provider")


class WebSearchProvider:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def search_text_resources(self, query: str, role: ContentRole = ContentRole.REFERENCE) -> list[PathResource]:
        """Tries multiple sources in order, since scraped search endpoints are unreliable
        (DDG's html endpoint frequently blocks/CAPTCHAs non-browser or datacenter traffic)."""
        for fetch_fn in (self._search_ddg_lite, self._search_ddg_html, self._search_wikipedia):
            try:
                resources = fetch_fn(query, role)
                if resources:
                    return resources
            except Exception as e:
                log.warning(f"{fetch_fn.__name__} failed for '{query}': {e}", exc_info=True)
        log.warning(f"All text resource sources exhausted with no results for '{query}'")
        return []

    def _search_ddg_lite(self, query: str, role: ContentRole) -> list[PathResource]:
        """lite.duckduckgo.com returns a plain HTML table and is much less aggressively
        rate-limited/blocked than the full html.duckduckgo.com endpoint."""
        encoded_query = urllib.parse.quote(f"{query} documentation guide tutorial")
        url = f"https://lite.duckduckgo.com/lite/?q={encoded_query}"

        resp = requests.post(url, headers=self.headers, timeout=8)
        if resp.status_code != 200:
            log.warning(f"DDG lite returned {resp.status_code} for '{query}': {resp.text[:200]}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        resources = []
        for link in soup.find_all("a", class_="result-link"):
            href = link.get("href", "")
            if not href.startswith("http"):
                continue
            title = link.get_text().strip() or f"{query} Reference"
            domain = urllib.parse.urlparse(href).netloc
            resources.append(PathResource(
                resource_type=ResourceType.ARTICLE,
                title=title[:80],
                url=href,
                role=role,
                justification="Technical writeup and documentation reference.",
                reading_time_minutes=10,
                source_domain=domain
            ))
            if len(resources) >= 3:
                break

        if not resources:
            log.warning(f"DDG lite returned 200 but no 'result-link' anchors for '{query}' — markup may have changed.")
        return resources

    def _search_ddg_html(self, query: str, role: ContentRole) -> list[PathResource]:
        """Original full html.duckduckgo.com scraper, kept as a secondary attempt."""
        encoded_query = urllib.parse.quote(f"{query} documentation guide tutorial")
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        resp = requests.get(url, headers=self.headers, timeout=8)
        if resp.status_code != 200:
            log.warning(f"DuckDuckGo html returned {resp.status_code} for '{query}': {resp.text[:200]}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.find_all("div", class_="result")
        if not results:
            log.warning(f"DuckDuckGo html returned 200 but no 'result' divs for '{query}' — likely blocked/CAPTCHA'd.")

        resources = []
        for res in results[:3]:
            snippet_tag = res.find("a", class_="result__snippet")
            url_tag = res.find("a", class_="result__url")
            if not snippet_tag or not url_tag:
                continue

            raw_href = url_tag.get("href", "")
            parsed_url = urllib.parse.urlparse(raw_href)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            final_url = query_params.get("uddg", [None])[0] or raw_href

            if not final_url.startswith("http"):
                continue

            domain = urllib.parse.urlparse(final_url).netloc
            resources.append(PathResource(
                resource_type=ResourceType.ARTICLE,
                title=snippet_tag.get_text().strip()[:80] or f"{query} Reference",
                url=final_url,
                role=role,
                justification="Technical writeup and documentation reference.",
                reading_time_minutes=10,
                source_domain=domain
            ))
        return resources

    def _search_wikipedia(self, query: str, role: ContentRole) -> list[PathResource]:
        """Last-resort real source: Wikipedia's public search API, no key/scraping needed."""
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": 3,
        }
        resp = requests.get(url, params=params, headers=self.headers, timeout=8)
        if resp.status_code != 200:
            log.warning(f"Wikipedia API returned {resp.status_code} for '{query}'")
            return []

        data = resp.json()
        resources = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", query)
            page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
            resources.append(PathResource(
                resource_type=ResourceType.ARTICLE,
                title=title,
                url=page_url,
                role=role,
                justification="Background reference material.",
                reading_time_minutes=8,
                source_domain="en.wikipedia.org"
            ))
        return resources