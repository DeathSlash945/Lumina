import requests
from config import OLLAMA_HOST, EMBED_MODEL


class EmbeddingModelUnavailable(Exception):
    pass


class EmbeddingClient:
    def __init__(self, host: str = OLLAMA_HOST, model: str = EMBED_MODEL):
        self.host = host.rstrip("/")
        self.model = model
        self._use_batched_endpoint = True  # flips to False permanently after first fallback

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._use_batched_endpoint:
            try:
                return self._embed_batched(texts)
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    # Older Ollama versions (pre batched-embed support) only
                    # have the singular /api/embeddings endpoint. Fall back
                    # permanently so we don't retry the dead route every call.
                    self._use_batched_endpoint = False
                else:
                    self._raise_clear_error(e)
        return self._embed_one_by_one(texts)

    def _embed_batched(self, texts: list[str]) -> list[list[float]]:
        resp = requests.post(
            f"{self.host}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]

    def _embed_one_by_one(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            resp = requests.post(
                f"{self.host}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=60,
            )
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                self._raise_clear_error(e)
            results.append(resp.json()["embedding"])
        return results

    def _raise_clear_error(self, e: requests.exceptions.HTTPError):
        body = e.response.text if e.response is not None else "(no response body)"
        raise EmbeddingModelUnavailable(
            f"Ollama embedding call failed ({e}). Response body: {body}\n"
            f"Most likely cause: the model '{self.model}' isn't pulled yet. "
            f"Run: ollama pull {self.model}"
        ) from e
