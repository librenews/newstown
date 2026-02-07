"""Reporter agent - researches and writes stories."""
from typing import Any
from agents.base import BaseAgent, AgentRole
from db import Task, TaskStage
from config.logging import get_logger
from config.settings import settings
import anthropic

logger = get_logger(__name__)


class ReporterAgent(BaseAgent):
    """Reporter agent that researches and drafts articles."""

    def __init__(self):
        super().__init__(AgentRole.REPORTER)
        self.llm = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def handle_task(self, task: Task) -> dict[str, Any]:
        """Handle research or draft tasks."""
        
        if task.stage == TaskStage.RESEARCH:
            return await self.research(task)
        elif task.stage == TaskStage.DRAFT:
            return await self.draft(task)
        else:
            raise ValueError(f"Reporter cannot handle stage: {task.stage}")

    async def research(self, task: Task) -> dict[str, Any]:
        """Research a story using web search and entity extraction."""
        detection_data = task.input.get("detection_data", {})
        
        title = detection_data.get("title", "")
        summary = detection_data.get("summary", "")
        original_url = detection_data.get("url", "")
        
        logger.info(
            "Researching story",
            story_id=str(task.story_id),
            title=title,
        )
        
        # Import here to avoid circular dependencies
        from ingestion import search_service, entity_extractor
        from db.human_oversight import human_prompt_store, source_store
        
        # Check for human prompts and custom sources (Phase 2)
        human_prompts = await human_prompt_store.get_pending_prompts(task.story_id)
        custom_sources = await source_store.get_story_sources(task.story_id)
        
        if human_prompts:
            logger.info(
                "Found human prompts for story",
                story_id=str(task.story_id),
                prompt_count=len(human_prompts),
            )
            # Mark prompts as being processed
            for prompt in human_prompts:
                await human_prompt_store.mark_processing(prompt.id)
        
        if custom_sources:
            logger.info(
                "Found custom sources for story",
                story_id=str(task.story_id),
                source_count=len(custom_sources),
            )
        
        # 1. Extract entities from the original detection
        entities_list = []
        if entity_extractor:  # May be None if spaCy unavailable
            entities_list = entity_extractor.extract(f"{title}. {summary}")
        
        entities = {
            "people": list(set(e.text for e in entities_list if e.label_ == "PERSON")),
            "organizations": list(set(e.text for e in entities_list if e.label_ == "ORG")),
            "locations": list(set(e.text for e in entities_list if e.label_ == "GPE")),
            "other": list(set(e.text for e in entities_list 
                             if e.label_ not in ["PERSON", "ORG", "GPE"])),
        }
        
        logger.info(
            "Entities extracted",
            people_count=len(entities["people"]),
            org_count=len(entities["organizations"]),
            location_count=len(entities["locations"]),
        )
        
        # 2. Search for corroborating sources
        search_results = await search_service.search(title, num_results=5)
        
        # 3. Build list of sources (original + search results + custom sources)
        sources = [
            {
                "url": original_url,
                "title": title,
                "snippet": summary[:200],
                "type": "original",
            }
        ]
        
        # Add search results
        for result in search_results:
            # Skip if it's the same domain as original
            if result.url != original_url:
                sources.append({
                    "url": result.url,
                    "title": result.title,
                    "snippet": result.snippet,
                    "type": "corroboration",
                })
        
        # Add human-provided sources (Phase 2)
        for custom_source in custom_sources:
            if custom_source.source_type == "url":
                sources.append({
                    "url": custom_source.source_url,
                    "title": custom_source.source_metadata.get("title", custom_source.source_url),
                    "snippet": "",
                    "type": "human_provided",
                    "source_id": custom_source.id,
                })
            elif custom_source.source_type in ["text", "document"]:
                sources.append({
                    "url": None,
                    "title": custom_source.source_metadata.get("filename", "Human-provided content"),
                    "snippet": (custom_source.source_content or "")[:200],
                    "type": "human_provided",
                    "source_id": custom_source.id,
                    "full_content": custom_source.source_content,
                })
            
            # Mark source as processed
            await source_store.mark_processed(custom_source.id)
        
        # 4. Basic multi-source verification
        # For MVP: just count sources and flag if only one
        source_count = len(sources)
        verified = source_count >= 2  # At least original + one corroborating source
        
        # 5. Extract key facts (simplified for MVP)
        facts = [
            {
                "claim": f"Story about: {title}",
                "source": original_url,
                "verified": verified,
                "source_count": source_count,
            }
        ]
        
        # Add entity-based facts
        if entities["people"]:
            facts.append({
                "claim": f"Involves: {', '.join(entities['people'][:3])}",
                "source": original_url,
                "verified": True,
                "entity_type": "PERSON",
            })
        
        if entities["organizations"]:
            facts.append({
                "claim": f"Organizations: {', '.join(entities['organizations'][:3])}",
                "source": original_url,
                "verified": True,
                "entity_type": "ORG",
            })
        
        # Answer human prompts if any (Phase 2)
        prompt_responses = []
        if human_prompts:
            for prompt in human_prompts:
                # Use LLM to answer the prompt based on research findings
                answer = await self._answer_prompt(
                    prompt.prompt_text,
                    context={
                        "title": title,
                        "summary": summary,
                        "sources": sources,
                        "facts": facts,
                        "entities": entities,
                    }
                )
                
                # Store the response
                await human_prompt_store.mark_answered(
                    prompt.id,
                    {
                        "answer": answer,
                        "sources_consulted": [s.get("url") or s.get("title") for s in sources[:5]],
                        "research_confidence": 0.8 if verified else 0.5,
                    }
                )
                
                prompt_responses.append({
                    "prompt_id": prompt.id,
                    "question": prompt.prompt_text,
                    "answer": answer,
                })
                
                logger.info(
                    "Answered human prompt",
                    prompt_id=prompt.id,
                    story_id=str(task.story_id),
                )
        
        # Log research completion
        await self.log_event(
            task.story_id,
            "research.completed",
            {
                "fact_count": len(facts),
                "source_count": len(sources),
                "entity_count": sum(len(v) for v in entities.values()),
                "verified": verified,
                "custom_sources_used": len(custom_sources),
                "prompts_answered": len(prompt_responses),
            },
        )
        
        logger.info(
            "Research completed",
            story_id=str(task.story_id),
            sources=len(sources),
            facts=len(facts),
            verified=verified,
            prompts_answered=len(prompt_responses),
        )
        
        return {
            "facts": facts,
            "sources": sources,
            "entities": entities,
            "verified": verified,
            "source_count": len(sources),
            "prompt_responses": prompt_responses,
        }

    async def _answer_prompt(self, question: str, context: dict[str, Any]) -> str:
        """Answer a human prompt using research context."""
        sources_text = "\n".join([
            f"- {s.get('title', 'Untitled')}: {s.get('snippet', s.get('full_content', 'No content'))[:150]}"
            for s in context["sources"][:5]
        ])
        
        facts_text = "\n".join([
            f"- {f['claim']}"
            for f in context["facts"][:5]
        ])
        
        prompt = f"""You are a research assistant helping a reporter answer a specific question.

Story: {context['title']}
Summary: {context['summary']}

Question: {question}

Research findings:
{facts_text}

Sources consulted:
{sources_text}

Entities identified:
- People: {', '.join(context['entities']['people'][:3]) or 'None'}
- Organizations: {', '.join(context['entities']['organizations'][:3]) or 'None'}

Answer the question based on the research findings. Be direct and cite sources when applicable.
If the research doesn't provide enough information to answer, say so clearly.
Keep your answer concise (2-3 sentences).
"""
        
        try:
            response = self.llm.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            
            return response.content[0].text
        except Exception as e:
            logger.error("Failed to answer prompt", error=str(e))
            return f"Unable to answer due to error: {str(e)}"

    async def draft(self, task: Task) -> dict[str, Any]:
        """Draft an article."""
        detection_data = task.input.get("detection_data", {})
        research_data = task.input.get("research_data", {})
        
        logger.info(
            "Drafting article",
            story_id=str(task.story_id),
            title=detection_data.get("title"),
        )
        
        # Use Claude to draft the article
        sources = research_data.get("sources", [])
        entities = research_data.get("entities", {})
        facts = research_data.get("facts", [])
        verified = research_data.get("verified", False)
        
        prompt = f"""You are a reporter writing a news article.

Title: {detection_data.get('title')}
Original Summary: {detection_data.get('summary')}
Source URL: {detection_data.get('url')}

Research Findings:
- Verified: {verified}
- Number of independent sources: {len(sources)}
- People involved: {', '.join(entities.get('people', [])[:5]) or 'None identified'}
- Organizations: {', '.join(entities.get('organizations', [])[:5]) or 'None identified'}
- Locations: {', '.join(entities.get('locations', [])[:5]) or 'None identified'}

Key facts:
{chr(10).join(f"- {fact['claim']}" for fact in facts[:5])}

Additional sources found:
{chr(10).join(f"- {s['title']}: {s['snippet'][:100]}..." for s in sources[1:4])}

Write a clear, factual news article (200-400 words) based on this information.
Include a headline and article body.
Cite sources appropriately.
If the story has only one source, note that it is unverified.
"""
        
        try:
            response = self.llm.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            
            article_text = response.content[0].text
            
            # Log draft completion
            await self.log_event(
                task.story_id,
                "draft.completed",
                {
                    "word_count": len(article_text.split()),
                    "model": "claude-3-5-sonnet-20241022",
                },
            )
            
            return {
                "article": article_text,
                "headline": detection_data.get("title"),
                "word_count": len(article_text.split()),
            }
            
        except Exception as e:
            logger.error("Draft generation failed", error=str(e))
            raise
