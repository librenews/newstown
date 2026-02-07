"""Editor agent - reviews and verifies articles."""
from typing import Any, List, Dict, Optional
import json
import asyncio
from uuid import UUID
from agents.base import BaseAgent, AgentRole
from db import Task, TaskStage, db
from db.articles import article_store
from config.logging import get_logger
from config.settings import settings
from ingestion.search_fallback import get_search
import anthropic

logger = get_logger(__name__)


class EditorAgent(BaseAgent):
    """Editor agent that reviews, verifies, and scores articles."""

    def __init__(self):
        super().__init__(AgentRole.EDITOR)
        # Use ChatService
        from agents.llm import chat_service
        self.chat_service = chat_service
        self.search_provider_instance = None # Lazy load

    @property
    def search_provider(self):
        if not self.search_provider_instance:
            self.search_provider_instance = get_search()
        return self.search_provider_instance

    async def handle_task(self, task: Task) -> dict[str, Any]:
        """Handle review tasks."""
        if task.stage == TaskStage.REVIEW:
            return await self.review_article(task)
        else:
            raise ValueError(f"Editor cannot handle stage: {task.stage}")

    # ... (review_article method) ...

    async def review_article(self, task: Task) -> dict[str, Any]:
        """Review an article draft."""
        draft = task.input.get("draft", {})
        article_text = draft.get("article", "")
        headline = draft.get("headline", "")
        
        logger.info(
            "Reviewing article",
            story_id=str(task.story_id),
            headline=headline,
        )

        # 1. Analyze text and extract claims
        analysis = await self._analyze_text(article_text)
        
        # 2. Verify claims
        verification_results = await self._verify_claims(analysis.get("claims", []))
        
        # 3. Calculate score
        score, verification_score, style_score = self._calculate_score(
            analysis, verification_results
        )
        
        # 4. Make decision
        decision = "APPROVE" if verification_score >= 0.8 and style_score >= 0.7 else "REJECT"
        
        # 5. Compile feedback
        feedback = self._compile_feedback(
            analysis, verification_results, score, decision
        )
        
        logger.info(
            "Review completed",
            decision=decision,
            score=score,
            story_id=str(task.story_id)
        )
        
        return {
            "decision": decision,
            "score": score,
            "verification_score": verification_score,
            "style_score": style_score,
            "feedback": feedback,
            "verification": verification_results,
            "analysis": analysis,
        }


    async def _analyze_text(self, text: str) -> dict[str, Any]:
        """Analyze text for claims, tone, and style."""
        prompt = f"""Analyze the following news article draft.
        
        Article:
        {text}
        
        Extract:
        1. List of factual claims made (max 10 key claims).
        2. Assessment of tone (Objective, Biased, Sensationalist, Dry).
        3. Assessment of style (conciseness, clarity, active voice).
        4. List of any grammatical or structural issues.
        
        Return JSON format:
        {{
            "claims": ["claim 1", "claim 2"],
            "tone": "Objective",
            "style_issues": ["issue 1"],
            "grammar_issues": ["issue 1"],
            "score": 0.0-1.0 (style score)
        }}
        """
        
        try:
            content = await self.chat_service.generate(
                system="You are an editor analyzing a news article.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            # Extract JSON from response (handle potential preamble)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end != -1:
                json_str = content[start:end]
                return json.loads(json_str)
            return {"claims": [], "tone": "Unknown", "score": 0.5}
        except Exception as e:
            logger.error("Text analysis failed", error=str(e))
            return {"claims": [], "tone": "Unknown", "score": 0.5}

    # ... (_verify_claims method) ...

    async def _verify_claims(self, claims: List[str]) -> dict[str, Any]:
        """Verify claims using search."""
        results = {}
        verified_count = 0
        
        for claim in claims[:5]:  # Limit to 5 verifications
            try:
                search_results = await self.search_provider.search(claim, max_results=3)
                context = "\n".join([r.snippet for r in search_results])
                check = await self._check_claim_support(claim, context)
                
                results[claim] = check
                if check["supported"]:
                    verified_count += 1
                    
            except Exception as e:
                logger.warning("Claim verification failed", claim=claim, error=str(e))
                results[claim] = {"supported": False, "reason": "Verification failed"}
        
        return {
            "claims_checked": len(claims[:5]),
            "verified_count": verified_count,
            "details": results
        }


    async def _check_claim_support(self, claim: str, context: str) -> dict[str, Any]:
        """Check if context supports the claim."""
        prompt = f"""Claim: {claim}
        
        Context:
        {context}
        
        Does the context support the claim?
        Return JSON: {{ "supported": true/false, "reason": "..." }}
        """
         
        try:
            content = await self.chat_service.generate(
                system="You are a fact-checker verifying a claim against context.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                model="claude-3-haiku-20240307",  # Preferred if using Anthropic
            )
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end != -1:
                return json.loads(content[start:end])
            return {"supported": False, "reason": "LLM output parse error"}
        except:
            return {"supported": False, "reason": "LLM check failed"}

    def _calculate_score(self, analysis: dict, verification: dict) -> tuple[float, float, float]:
        """Calculate overall quality score."""
        style_score = analysis.get("score", 0.5)
        
        claims_checked = verification.get("claims_checked", 0)
        verified = verification.get("verified_count", 0)
        
        verification_score = 1.0
        if claims_checked > 0:
            verification_score = verified / claims_checked
            
        # Weighted score: 60% verification, 40% style
        total_score = (verification_score * 0.6) + (style_score * 0.4)
        
        return round(total_score, 2), verification_score, style_score

    def _compile_feedback(
        self, analysis: dict, verification: dict, score: float, decision: str
    ) -> str:
        """Create human-readable feedback."""
        parts = [
            f"Decision: {decision} (Score: {score}/1.0)",
            f"Style Score: {analysis.get('score', 0)}",
            f"Fact Check: {verification.get('verified_count', 0)}/{verification.get('claims_checked', 0)} verified",
            "",
            "Style Issues:",
        ]
        parts.extend([f"- {i}" for i in analysis.get("style_issues", [])])
        
        parts.append("\\nUnverified Claims:")
        for claim, detail in verification.get("details", {}).items():
            if not detail.get("supported"):
                parts.append(f"- {claim}: {detail.get('reason')}")
                
        return "\\n".join(parts)
