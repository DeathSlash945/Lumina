import json
import requests
from config import OLLAMA_HOST, CHAT_MODEL
from retrieval.schemas import ContentRole

class ChatModelUnavailable(Exception):
    pass

class LLMClient:
    def __init__(self, host: str = OLLAMA_HOST, model: str = CHAT_MODEL):
        self.host = host.rstrip("/")
        self.model = model

    def _chat_json(self, system: str, user: str) -> dict:
        try:
            resp = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "format": "json",
                    "stream": False,
                    "think": False,  # Explicitly disable to avoid latency loops in reasoning variants
                    "options": {"temperature": 0.2},
                },
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise ChatModelUnavailable(
                f"Could not connect to Ollama at {self.host}. Is it running? Try: ollama serve"
            ) from e
        except requests.exceptions.Timeout as e:
            raise ChatModelUnavailable(
                f"Ollama call to '{self.model}' timed out after 120s."
            ) from e
        except requests.exceptions.HTTPError as e:
            body = e.response.text if e.response is not None else "(no body)"
            raise ChatModelUnavailable(
                f"Ollama chat call failed ({e}). Response body: {body}"
            ) from e

        content = resp.json()["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ChatModelUnavailable(
                f"Model returned non-JSON content despite format=json request: {content[:300]!r}"
            ) from e

    def score_for_role(self, topic: str, role: ContentRole, chunk_text: str) -> tuple[float, str]:
        """
        Judges the contextual alignment of a scraped source against the active 
        pedagogical role chosen by the curriculum generation weights.
        """
        role_hint = {
            ContentRole.FOUNDATIONAL: "a clear beginner-level explanation of the concept",
            ContentRole.DEEP_DIVE: "a deeper, more advanced or mathematical treatment",
            ContentRole.PRACTICE: "a worked example, problem, or hands-on application",
            ContentRole.REFERENCE: "reference material, common mistakes, or a concise summary",
        }[role]
        
        system = (
            f"You judge whether a content excerpt genuinely serves as {role_hint} "
            "for a learner studying the given topic -- not just whether it mentions the topic.\n"
            'Respond ONLY with a JSON object: {"score": <0.0-1.0>, "reason": "<one short sentence>"}'
        )
        user = f"Topic: {topic}\n\nContent excerpt:\n{chunk_text[:2000]}"
        try:
            result = self._chat_json(system, user)
            return float(result.get("score", 0.0)), result.get("reason", "")
        except Exception:
            return 0.0, "Relevance evaluation pipeline error."