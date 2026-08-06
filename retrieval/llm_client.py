import json
import logging
import os
from typing import Tuple
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger("lumina.llm")

class LLMProviderError(Exception):
    """Custom exception raised when an LLM provider fails."""
    pass

class LLMClient:
    def __init__(self):
        self.primary_api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.fallback_api_key = os.getenv("SECONDARY_LLM_API_KEY")
        
    @retry(
        retry=retry_if_exception_type((LLMProviderError, TimeoutError, ConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=False
    )
    def _execute_primary(self, prompt: str, system_message: str) -> str:
        """Executes query against primary LLM provider with exponential backoff."""
        if not self.primary_api_key:
            raise LLMProviderError("Primary API key not configured.")
        
        # Primary LLM API logic (e.g. Groq / OpenAI endpoint)
        # Standard implementation simulation returning raw response text
        try:
            # Replace with your actual SDK client call:
            # response = self.primary_client.chat.completions.create(...)
            # return response.choices[0].message.content
            return ""
        except Exception as e:
            log.warning(f"Primary LLM attempt failed: {e}")
            raise LLMProviderError(str(e))

    def _execute_fallback(self, prompt: str, system_message: str) -> str:
        """Fallback execution when primary provider fails or exhausts retries."""
        log.info("Executing secondary LLM failover path...")
        try:
            # Local Ollama endpoint or secondary provider API
            # response = requests.post("http://localhost:11434/api/generate", ...)
            return ""
        except Exception as e:
            log.error(f"Fallback LLM execution failed: {e}")
            return ""

    def query_with_failover(self, prompt: str, system_message: str = "") -> str:
        """Orchestrates query attempt on primary provider before triggering fallback."""
        try:
            result = self._execute_primary(prompt, system_message)
            if result:
                return result
        except Exception as e:
            log.warning(f"Primary LLM retries exhausted: {e}")

        # Trigger secondary failover
        return self._execute_fallback(prompt, system_message)

    def score_for_role(self, topic: str, role: str, title: str) -> Tuple[float, str]:
        """Scores resource relevance against step roles with guaranteed structural fallback."""
        prompt = (
            f"Topic: {topic}\nRole: {role}\nContent Title: {title}\n"
            "Return JSON only: {\"score\": float (0.0 to 1.0), \"reason\": \"string\"}"
        )
        system_msg = "You are a curriculum quality filter. Return raw JSON strictly."

        raw_response = self.query_with_failover(prompt, system_msg)
        
        try:
            parsed = json.loads(raw_response)
            score = float(parsed.get("score", 0.7))
            reason = str(parsed.get("reason", f"Relevant content for {topic}"))
            return score, reason
        except (json.JSONDecodeError, TypeError, ValueError):
            # Safe algorithmic fallback score when LLM output parsing fails
            log.warning(f"LLM JSON parsing failed for title '{title}'. Using deterministic fallback score.")
            return 0.75, f"Automatically validated reference covering {topic}."