"""
Web Search Provider for text, book references, and canonical documentation.
Scrapes clean text results from public search engines without needing heavy API keys.
"""
import urllib.parse
import requests
from bs4 import BeautifulSoup
from retrieval.schemas import ContentRole, PathResource, ResourceType

class WebSearchProvider:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def search_text_resources(self, query: str, role: ContentRole) -> list[PathResource]:
        """
        Queries HTML search frontends to locate open text documents,
        academic cheat sheets, and technical guides matching the sub-queries.
        """
        encoded_query = urllib.parse.quote(f"{query} tutorial documentation filetype:html")
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        resources = []
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                return []
            
            soup = BeautifulSoup(resp.text, "html.parser")
            # Pull clean organic search results from the engine output
            links = soup.find_all("a", class_="result__url")
            titles = soup.find_all("a", class_="result__snippet")
            
            for link, title_tag in zip(links[:3], titles[:3]):
                raw_href = link.get("href", "")
                # Parse out trackable out-bound destination URLs
                parsed_url = urllib.parse.urlparse(raw_href)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                final_url = query_params.get("uddg", [None])[0]
                if not final_url:
                    continue
                    
                domain = urllib.parse.urlparse(final_url).netloc
                
                # Assign formatting types dynamically based on canonical tags
                res_type = ResourceType.TEXT_ARTICLE
                if "book" in final_url or "edu" in domain:
                    res_type = ResourceType.BOOK_PART
                
                resources.append(PathResource(
                    resource_type=res_type,
                    title=title_tag.get_text().strip()[:80] or "Documentation Reference",
                    url=final_url,
                    role=role,
                    justification="Comprehensive written breakdown matching technical concepts.",
                    reading_time_minutes=8,
                    source_domain=domain
                ))
        except Exception:
            pass # Gracefully handle lookup interruptions or parsing updates
            
        return resources