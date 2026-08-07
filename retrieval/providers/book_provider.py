import logging
import requests
from retrieval.schemas import PathResource, ResourceType, ContentRole

log = logging.getLogger("lumina.books")

class MultiSourceBookProvider:
    @staticmethod
    def fetch_google_books(topic: str, role: ContentRole = ContentRole.REFERENCE, limit: int = 2) -> list[PathResource]:
        try:
            url = f"https://www.googleapis.com/books/v1/volumes?q={requests.utils.quote(topic)}&maxResults={limit}&orderBy=relevance"
            headers = {"User-Agent": "Mozilla/5.0 (compatible; LuminaBot/1.0)"}
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                log.warning(f"Google Books API returned {resp.status_code} for '{topic}': {resp.text[:300]}")
                return []
            res = resp.json()

            if "items" not in res:
                log.info(f"Google Books API returned zero results for '{topic}' (totalItems={res.get('totalItems', 0)}).")
                return []

            resources = []
            for item in res.get("items", []):
                info = item.get("volumeInfo", {})
                title = info.get("title", topic)
                authors = ", ".join(info.get("authors", ["Technical Author"]))
                avg_rating = float(info.get("averageRating", 4.5))
                link = info.get("infoLink") or info.get("previewLink") or "https://books.google.com"
                
                resources.append(PathResource(
                    resource_type=getattr(ResourceType, "BOOK", ResourceType.DOCUMENTATION),
                    title=f"Book: {title}",
                    url=link,
                    role=role,
                    justification=f"Authoritative text covering {topic}.",
                    rating=avg_rating,
                    source_platform="Google Books",
                    author_or_channel=authors
                ))
            return resources
        except Exception as e:
            log.warning(f"Google Books fetch failed for {topic}: {e}", exc_info=True)
            return []

    def search(self, query: str, limit: int = 2, role: ContentRole = ContentRole.REFERENCE) -> list[PathResource]:
        return self.fetch_google_books(query, role=role, limit=limit)