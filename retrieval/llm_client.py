import os
import json
import re
import logging
import requests
from typing import Any, Dict, List, Union
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from dotenv import load_dotenv
load_dotenv()
log = logging.getLogger("lumina.llm")

class LLMProviderError(Exception):
    """Custom exception for LLM provider failures."""
    pass

class LLMClient:
    def __init__(
        self, 
        api_key: str = None,
        primary_api_url: str = "https://api.groq.com/openai/v1/chat/completions",
        primary_model: str = "llama-3.3-70b-versatile",
        fallback_model: str = "llama-3.1-8b-instant"
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.primary_api_url = primary_api_url
        self.primary_model = primary_model
        self.fallback_model = fallback_model

    def _extract_json(self, raw_text: str) -> Union[Dict[str, Any], List[Any]]:
        """Cleans markdown formatting and extracts valid JSON payload."""
        cleaned = re.sub(r'```json\s*|\s*```', '', raw_text).strip()
        
        json_match = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)
            
        return json.loads(cleaned)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=6),
        retry=retry_if_exception_type(LLMProviderError),
        reraise=True  # Reraise underlying LLMProviderError so query_with_failover catches the true cause
    )
    def _call_provider(self, prompt: str, model: str, system_prompt: str = "") -> str:
        """Executes HTTP POST request to Groq API using OpenAI-compatible format."""
        if not self.api_key:
            raise LLMProviderError("GROQ_API_KEY is missing. Ensure it is set in environment variables.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Groq requires the prompt or system prompt to contain the word 'json' when response_format is json_object
        sys_message = system_prompt if system_prompt else "You are an AI assistant that outputs structured json."
        if "json" not in sys_message.lower():
            sys_message += " Always respond in valid json format."

        messages = [
            {"role": "system", "content": sys_message},
            {"role": "user", "content": prompt}
        ]

        payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            response = requests.post(
                self.primary_api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            err_msg = response.text if 'response' in locals() and hasattr(response, 'text') else str(e)
            log.error(f"Groq API call error details [{model}]: {err_msg}")
            raise LLMProviderError(f"Groq API call failed for model '{model}': {err_msg}")

    def query_with_failover(self, prompt: str, system_prompt: str = "") -> str:
        """Executes prompt against primary model, failing over to fallback model on error."""
        try:
            return self._call_provider(prompt, self.primary_model, system_prompt)
        except Exception as primary_err:
            log.warning(f"Primary model ({self.primary_model}) failed: {primary_err}. Failing over to ({self.fallback_model})...")
            try:
                return self._call_provider(prompt, self.fallback_model, system_prompt)
            except Exception as fallback_err:
                log.error(f"Fallback model ({self.fallback_model}) failed: {fallback_err}")
                return "{}"

    def _chat_json(self, prompt: str, system_prompt: str = "") -> Union[Dict[str, Any], List[Any]]:
        """Public JSON query interface used by planner and retrieval modules."""
        raw_response = self.query_with_failover(prompt, system_prompt)
        
        try:
            return self._extract_json(raw_response)
        except (json.JSONDecodeError, TypeError) as err:
            log.warning(f"Failed to parse Groq JSON response: {err}. Returning empty dict.")
            return {}

    def score_for_role(self, resource_text: str, role: str, *args, **kwargs) -> tuple[float, str]:
        """
        Scores resource suitability for a given learning path role.
        Accepts *args and **kwargs to maintain signature compatibility with orchestrator callers.
        """
        prompt = (
            f"Rate the relevance (0.0 to 1.0) of this content for role '{role}':\n"
            f"{resource_text[:500]}\n"
            f"Respond in JSON format: {{\"score\": float, \"reason\": string}}"
        )
        res = self._chat_json(prompt)
        
        if isinstance(res, dict):
            score = float(res.get("score", 0.7))
            reason = str(res.get("reason", "Relevant resource match."))
        else:
            score, reason = 0.7, "Relevant resource match."
            
        return score, reason