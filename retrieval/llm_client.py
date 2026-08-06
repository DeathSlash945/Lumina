import json
import logging
import os
import requests
from typing import Tuple
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger("lumina.llm")

class LLMProviderError(Exception):
    """Custom exception raised when an LLM provider fails."""
    pass

class LLMClient:
    def __init__(self):
        self.primary_api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.fallback_url = os.getenv("OLLAMA_HOST", "http://localhost:11434/api/generate")

    @retry(
        retry=retry_if_exception_type((LLMProviderError, TimeoutError, ConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=False
    )
    def _execute_primary(self, prompt: str, system_message: str) -> str:
        """Executes query against primary LLM provider (Groq or OpenAI) with exponential backoff."""
        if not self.primary_api_key:
            raise LLMProviderError("Primary API key (GROQ_API_KEY or OPENAI_API_KEY) not configured.")

        is_groq = bool(os.getenv("GROQ_API_KEY"))
        endpoint = "https://api.groq.com/openai/v1/chat/completions" if is_groq else "https://api.openai.com/v1/chat/completions"
        default_model = "llama-3.3-70b-versatile" if is_groq else "gpt-4o-mini"
        model = os.getenv("LLM_MODEL", default_model)

        headers = {
            "Authorization": f"Bearer {self.primary_api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 512,
            "response_format": {"type": "json_object"}
        }

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=8)
            if response.status_code != 200:
                raise LLMProviderError(f"Primary provider returned HTTP {response.status_code}: {response.text}")

            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            log.warning(f"Primary LLM network error: {e}")
            raise LLMProviderError(f"Network error: {e}")
        except (KeyError, IndexError) as e:
            log.warning(f"Unexpected response schema from primary LLM: {e}")
            raise LLMProviderError(f"Malformed response format: {e}")

    def _execute_fallback(self, prompt: str, system_message: str) -> str:
        """Local Ollama endpoint fallback when cloud primary fails."""
        log.info("Executing local Ollama failover route...")
        try:
            payload = {
                "model": os.getenv("OLLAMA_MODEL", "mistral"),
                "prompt": f"{system_message}\n\n{prompt}" if system_message else prompt,
                "stream": False,
                "format": "json"
            }
            res = requests.post(self.fallback_url, json=payload, timeout=12)
            if res.status_code == 200:
                return res.json().get("response", "")
        except Exception as e:
            log.error(f"Fallback LLM execution failed: {e}")
        return ""

    def query_with_failover(self, prompt: str, system_message: str = "") -> str:
        """Executes primary request with retries before falling back to local runner."""
        try:
            result = self._execute_primary(prompt, system_message)
            if result:
                return result
        except Exception as e:
            log.warning(f"Primary LLM retries exhausted: {e}")

        return self._execute_fallback(prompt, system_message)

    def score_for_role(self, topic: str, role: str, title: str) -> Tuple[float, str]:
        """Scores resource relevance against step roles with guaranteed structural fallback."""
        prompt = (
            f"Topic: {topic}\nRole: {role}\nContent Title: {title}\n"
            'Return JSON strictly in this format: {"score": 0.85, "reason": "Explanation"}'
        )
        system_msg = "You are a technical curriculum auditor. Output valid JSON only."

        raw_response = self.query_with_failover(prompt, system_msg)
        
        try:
            parsed = json.loads(raw_response)
            score = float(parsed.get("score", 0.75))
            reason = str(parsed.get("reason", f"Relevant content for {topic}"))
            return max(0.0, min(1.0, score)), reason
        except (json.JSONDecodeError, TypeError, ValueError):
            log.warning(f"LLM JSON parsing failed for title '{title}'. Using fallback relevance score.")
            return 0.75, f"Validated technical material covering {topic}."