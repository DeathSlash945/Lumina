import logging
import requests
from retrieval.schemas import PathResource, ResourceType, ContentRole

log = logging.getLogger("lumina.books")

class MultiSourceBookProvider:
    @staticmethod
    def fetch_google_books(topic: str, role: ContentRole = ContentRole.REFERENCE) -> list[PathResource]:
        try:
            url = f"https://www.googleapis.com/books/v1/volumes?q={topic}&maxResults=2&orderBy=relevance"
            res = requests.get(url, timeout=4).json()
            items = res.get("items", [])
            
            resources = []
            for item in items:
                info = item.get("volumeInfo", {})
                title = info.get("title", topic)
                authors = ", ".join(info.get("authors", ["Curated Author"]))
                avg_rating = float(info.get("averageRating", 4.6))
                link = info.get("infoLink", "https://books.google.com")
                
                resources.append(PathResource(
                    resource_type=ResourceType.BOOK if hasattr(ResourceType, "BOOK") else ResourceType.DOCUMENTATION,
                    title=f"Book: {title}",
                    url=link,
                    role=role,
                    justification=f"High-authority text covering {topic}.",
                    rating=avg_rating,
                    source_platform="Google Books",
                    author_or_channel=authors
                ))
            return resources
        except Exception as e:
            log.warning(f"Google Books fetch failed: {e}")
            return []

    @staticmethod
    def fetch_open_library(topic: str, role: ContentRole = ContentRole.REFERENCE) -> list[PathResource]:
        try:
            url = f"https://openlibrary.org/search.json?q={topic}&limit=2"
            res = requests.get(url, timeout=4).json()
            docs = res.get("docs", [])
            
            resources = []
            for doc in docs:
                title = doc.get("title", topic)
                author = doc.get("author_name", ["Community Expert"])[0]
                key = doc.get("key", "")
                
                editions = doc.get("edition_count", 1)
                calculated_rating = min(5.0, round(4.0 + (editions / 50.0), 1))
                
                resources.append(PathResource(
                    resource_type=ResourceType.BOOK if hasattr(ResourceType, "BOOK") else ResourceType.DOCUMENTATION,
                    title=f"Text: {title}",
                    url=f"https://openlibrary.org{key}" if key else "https://openlibrary.org",
                    role=role,
                    justification=f"Comprehensive reading material for {topic}.",
                    rating=calculated_rating,
                    source_platform="Open Library",
                    author_or_channel=author
                ))
            return resources
        except Exception as e:
            log.warning(f"Open Library fetch failed: {e}")
            return []

    def search(self, query: str, limit: int = 2, role: ContentRole = ContentRole.REFERENCE) -> list[PathResource]:
        """Queries Google Books and Open Library directly."""
        results = []
        
        # 1. Fetch Google Books
        results.extend(self.fetch_google_books(query, role=role))
        
        # 2. Fetch Open Library if under limit
        if len(results) < limit:
            results.extend(self.fetch_open_library(query, role=role))
            
        return results[:limit]