"""LLM abstraction layer."""
from typing import List, Dict, Any, Optional
import openai
import anthropic
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


class ChatService:
    """
    Unified interface for chat completions.
    
    Supports:
    1. Anthropic (default for production/high-quality)
    2. OpenAI-compatible Local LLMs (via settings.local_llm_base_url)
    """

    def __init__(self):
        self.provider = "anthropic"
        self.client: Any = None
        
        if settings.local_llm_base_url:
            self.provider = "local"
            logger.info(f"Initializing ChatService with LOCAL provider at {settings.local_llm_base_url}")
            self.client = openai.AsyncOpenAI(
                base_url=settings.local_llm_base_url,
                api_key="sk-local-key",  # Usually ignored by local runners
            )
        else:
            self.provider = "anthropic"
            logger.info("Initializing ChatService with ANTHROPIC provider")
            self.client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
            )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system: str = "",
        model: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            messages: List of {"role": "user/assistant", "content": "..."}
            system: System prompt
            model: Model name override (optional)
            max_tokens: Max output tokens
            temperature: Sampling temperature
            
        Returns:
            Generated text content
        """
        try:
            if self.provider == "anthropic":
                # Use configured model or default to Sonnet
                target_model = model or settings.claude_model
                
                # Anthropic expects system as a separate parameter, not in messages
                response = await self.client.messages.create(
                    model=target_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=messages,
                )
                return response.content[0].text
                
            elif self.provider == "local":
                # Use configured local model, ignoring the specific model requested (which is likely optimal for Anthropic/OpenAI)
                target_model = settings.local_llm_model
                
                # Convert system prompt to a message for OpenAI format
                full_messages = []
                if system:
                    full_messages.append({"role": "system", "content": system})
                full_messages.extend(messages)
                
                response = await self.client.chat.completions.create(
                    model=target_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=full_messages,
                )
                return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"LLM generation failed ({self.provider}): {e}")
            raise

        return ""


# Global instance
chat_service = ChatService()
