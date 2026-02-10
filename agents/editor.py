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
        """Review an article draft with advanced AP style check and persistence."""
        from db.governance import article_review_store
        
        draft = task.input.get("draft", {})
        article_text = draft.get("article", "")
        headline = draft.get("headline", "")
        article_id = task.input.get("article_id") # Usually None for drafts
        
        logger.info(
            "Advanced Review started",
            story_id=str(task.story_id),
            headline=headline,
        )

        # 1. Analyze text (Tone, Style, AP Standards)
        analysis = await self._analyze_text(article_text)
        
        # 2. Verify claims (Fact-checking)
        verification_results = await self._verify_claims(analysis.get("claims", []))
        
        # 3. Source Diversity Check
        sources = task.input.get("research_data", {}).get("sources", [])
        diversity_score = self._check_source_diversity(sources)

        # 4. Calculate scores
        score, verification_score, style_score = self._calculate_score(
            analysis, verification_results
        )
        
        # Apply diversity penalty
        if diversity_score < 0.5:
            score = round(score * 0.8, 2)
            analysis["style_issues"].append("Poor source diversity - story relies on too few domains.")

        # 5. Make decision
        # Higher thresholds for Phase 4.5 - diversity must be decent
        decision = "APPROVE" if verification_score >= 0.9 and style_score >= 0.8 and diversity_score >= 0.5 else "REJECT"
        
        # 5. Compile feedback
        feedback = self._compile_feedback(
            analysis, verification_results, score, decision
        )
        
        # 6. PERSIST to article_reviews
        try:
            await article_review_store.create(
                story_id=task.story_id,
                editor_agent_id=self.agent_id,
                score=score,
                decision=decision,
                article_id=UUID(article_id) if article_id else None,
                verification_score=verification_score,
                style_score=style_score,
                feedback=feedback,
                meta={
                    "tone": analysis.get("tone"),
                    "claims_count": len(analysis.get("claims", [])),
                    "ap_style_violations": len(analysis.get("ap_violations", []))
                }
            )
        except Exception as e:
            logger.error("Failed to persist review", error=str(e))

        logger.info(
            "Review completed and persisted",
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
        """Analyze text for claims, tone, and strict AP Style standards."""
        prompt = f"""Analyze the following news article draft for quality and AP Style adherence.
        
        Article:
        {text}
        
        Instructions:
        1. Extract max 10 key factual claims for verification.
        2. Assess tone (Objective, Biased, Sensationalist, Dry).
        3. Check for AP Style violations (e.g., date formats, title capitalization, number usage, Oxford commas - AP doesn't use them).
        4. Identify grammatical or structural issues.
        5. Provide a style score (0.0 to 1.0) based on overall quality and AP adherence.
        
        Return JSON format:
        {{
            "claims": ["claim 1", "claim 2"],
            "tone": "Objective",
            "ap_violations": ["violation 1", "violation 2"],
            "style_issues": ["issue 1"],
            "grammar_issues": ["issue 1"],
            "score": 0.85
        }}
        """
        
        try:
            content = await self.chat_service.generate(
                system="You are a professional news editor enforcing strict AP Style guidelines.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            # Extract JSON from response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end != -1:
                json_str = content[start:end]
                return json.loads(json_str)
            return {"claims": [], "tone": "Unknown", "score": 0.5, "ap_violations": []}
        except Exception as e:
            logger.error("Text analysis failed", error=str(e))
            return {"claims": [], "tone": "Unknown", "score": 0.5, "ap_violations": []}

    async def _verify_claims(self, claims: List[str]) -> dict[str, Any]:
        """Verify claims using search."""
        results = {}
        verified_count = 0
        
        # Phase 4.1: Multi-pass check - verify more claims for deeper reliability
        limit = 7 
        claims_to_check = claims[:limit]
        
        for claim in claims_to_check:
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
            "claims_checked": len(claims_to_check),
            "verified_count": verified_count,
            "details": results
        }

    async def _check_claim_support(self, claim: str, context: str) -> dict[str, Any]:
        """Check if context supports the claim."""
        prompt = f"""Claim: {claim}
        
        Context:
        {context}
        
        Does the context support the claim? Be strict.
        Return JSON: {{ "supported": true/false, "reason": "..." }}
        """
         
        try:
            content = await self.chat_service.generate(
                system="You are an expert fact-checker. Be pedantic and thorough.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
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
        style_base_score = analysis.get("score", 0.5)
        ap_violations_count = len(analysis.get("ap_violations", []))
        
        # Penalty for AP style violations
        style_score = max(0, style_base_score - (ap_violations_count * 0.05))
        
        claims_checked = verification.get("claims_checked", 0)
        verified = verification.get("verified_count", 0)
        
        verification_score = 1.0
        if claims_checked > 0:
            verification_score = verified / claims_checked
            
        # Weighted score: 70% verification, 30% style for advanced editor
        total_score = (verification_score * 0.7) + (style_score * 0.3)
        
        return round(total_score, 2), verification_score, style_score

    def _compile_feedback(
        self, analysis: dict, verification: dict, score: float, decision: str
    ) -> str:
        """Create human-readable feedback."""
        parts = [
            f"Decision: {decision} (Score: {score}/1.0)",
            f"Style/AP Score: {analysis.get('score', 0)}",
            f"Fact Check: {verification.get('verified_count', 0)}/{verification.get('claims_checked', 0)} verified",
            "",
            "AP Style Violations:",
        ]
        parts.extend([f"- {i}" for i in analysis.get("ap_violations", [])])
        
        parts.append("\nStyle/Grammar Issues:")
        parts.extend([f"- {i}" for i in analysis.get("style_issues", [])])
        parts.extend([f"- {i}" for i in analysis.get("grammar_issues", [])])
        
        parts.append("\nUnverified Claims:")
        for claim, detail in verification.get("details", {}).items():
            if not detail.get("supported"):
                parts.append(f"- {claim}: {detail.get('reason')}")
                
        return "\n".join(parts)

    def _check_source_diversity(self, sources: list[dict]) -> float:
        """Measure how many unique top-level domains provide context."""
        if not sources:
            return 0.0
        
        from urllib.parse import urlparse
        domains = set()
        for s in sources:
            url = s.get("url")
            if url:
                netloc = urlparse(url).netloc
                if netloc:
                    domains.add(netloc)
        
        # 1 domain = 0.0, 2 domains = 0.5, 3+ domains = 1.0
        if len(domains) <= 1: return 0.0
        if len(domains) == 2: return 0.5
        return 1.0
