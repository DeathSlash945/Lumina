import logging
import requests
from retrieval.schemas import PathResource, ResourceType, ContentRole

log = logging.getLogger("lumina.books")

#goes to google books to find material, returns none if doesnt find anything
#have to refine ts but will do later
class MultiSourceBookProvider:
    @staticmethod
    def fetch_google_books(topic: str, role: ContentRole = ContentRole.REFERENCE, limit: int = 2) -> list[PathResource]:
        try:
            # Clean topic to remove noisy filler terms for Google Books API
            cleaned_topic = (
                topic.replace("Overview", "")
                     .replace("Introduction to", "")
                     .replace("Platform", "")
                     .strip()
            )
            
            # Query with topic and computer/tech subject scoping
            formatted_query = requests.utils.quote(f'"{cleaned_topic}" subject:"computers"')
            url = f"https://www.googleapis.com/books/v1/volumes?q={formatted_query}&maxResults={limit}&orderBy=relevance"
            headers = {"User-Agent": "Mozilla/5.0 (compatible; LuminaBot/1.0)"}
            resp = requests.get(url, headers=headers, timeout=8)
            
            res = {}
            if resp.status_code == 200:
                res = resp.json()

            # Fallback to loose query without subject filter if narrow search hits zero
            if "items" not in res:
                loose_query = requests.utils.quote(cleaned_topic)
                url = f"https://www.googleapis.com/books/v1/volumes?q={loose_query}&maxResults={limit}&orderBy=relevance"
                resp = requests.get(url, headers=headers, timeout=8)
                if resp.status_code == 200:
                    res = resp.json()

            if "items" not in res:
                log.info(f"Google books API returned zero results for '{topic}'. Trying Open Library...")
                return MultiSourceBookProvider.fetch_open_library(cleaned_topic, role, limit)

            resources = []
            for item in res.get("items", []):
                info = item.get("volumeInfo", {})
                title = info.get("title", topic)
                authors = ", ".join(info.get("authors", ["Technical author"]))
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
            log.warning(f"Google books fetch failed for {topic}: {e}", exc_info=True)
            return []

    # backup open library query in case google books API comes up empty
    @staticmethod
    def fetch_open_library(topic: str, role: ContentRole = ContentRole.REFERENCE, limit: int = 2) -> list[PathResource]:
        try:
            url = f"https://openlibrary.org/search.json?q={requests.utils.quote(topic)}&limit={limit}"
            resp = requests.get(url, timeout=8)
            if resp.status_code != 200:
                return []
            
            docs = resp.json().get("docs", [])
            resources = []
            for doc in docs:
                title = doc.get("title", topic)
                authors = ", ".join(doc.get("author_name", ["Technical Author"])[:2])
                key = doc.get("key", "")
                link = f"https://openlibrary.org{key}" if key else "https://openlibrary.org"

                resources.append(PathResource(
                    resource_type=getattr(ResourceType, "BOOK", ResourceType.DOCUMENTATION),
                    title=f"Book: {title}",
                    url=link,
                    role=role,
                    justification=f"Reference text for {topic}.",
                    rating=4.3,
                    source_platform="Open Library",
                    author_or_channel=authors
                ))
            return resources
        except Exception as e:
            log.warning(f"OpenLibrary fetch failed for '{topic}': {e}")
            return []

    def search(self, query: str, limit: int = 2, role: ContentRole = ContentRole.REFERENCE) -> list[PathResource]:
        return self.fetch_google_books(query, role=role, limit=limit)