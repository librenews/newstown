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
        # Use ChatService abstraction
        from agents.llm import chat_service
        self.chat_service = chat_service

    async def handle_task(self, task: Task) -> dict[str, Any]:
        """Handle research or draft tasks."""
        
        if task.stage == TaskStage.RESEARCH:
            return await self.research(task)
        elif task.stage == TaskStage.DRAFT:
            return await self.draft(task)
        elif task.stage == TaskStage.EDIT:
            return await self.revise(task)
        else:
            raise ValueError(f"Reporter cannot handle stage: {task.stage}")

    async def research(self, task: Task) -> dict[str, Any]:
        """Research a story using web search, memory, and entity extraction."""
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
        from ingestion.embeddings import embedding_service
        from db.human_oversight import human_prompt_store, source_store
        from db.memory import memory_store
        
        # Check for human prompts and custom sources
        human_prompts = await human_prompt_store.get_pending_prompts(task.story_id)
        custom_sources = await source_store.get_story_sources(task.story_id)
        
        if human_prompts:
            # Mark prompts as being processed
            for prompt in human_prompts:
                await human_prompt_store.mark_processing(prompt.id)
        
        # 1. Extract entities
        entities_list = []
        if entity_extractor:
            entities_list = entity_extractor.extract(f"{title}. {summary}")
        
        entities = {
            "people": list(set(e.text for e in entities_list if e.label_ == "PERSON")),
            "organizations": list(set(e.text for e in entities_list if e.label_ == "ORG")),
            "locations": list(set(e.text for e in entities_list if e.label_ == "GPE")),
            "other": list(set(e.text for e in entities_list 
                             if e.label_ not in ["PERSON", "ORG", "GPE"])),
        }
        
        # 2. Contextual Memory Retrieval (Long-Term Memory)
        historical_context = []
        try:
            # Generate embedding for the new story
            embedding = embedding_service.embed(f"{title}. {summary}")
            
            # Find similar past stories
            similar_memories = await memory_store.find_similar_stories(
                embedding, threshold=0.75, limit=3
            )
            
            for memory in similar_memories:
                if str(memory["story_id"]) != str(task.story_id):
                    historical_context.append({
                        "content": memory["content"],
                        "similarity": memory["similarity"]
                    })
        except Exception as e:
            logger.warning("Contextual retrieval failed", error=str(e))

        # 3. Search for verifying information (Entity-First Strategy)
        search_results = []
        
        # A. Main topic search
        main_results = await search_service.search(title, num_results=3)
        search_results.extend(main_results)
        
        # B. Entity specific search
        for person in entities["people"][:1]:
            entity_results = await search_service.search(f"{person} {title}", num_results=2)
            search_results.extend(entity_results)
            
        for org in entities["organizations"][:1]:
            entity_results = await search_service.search(f"{org} news", num_results=2)
            search_results.extend(entity_results)

        # Deduplicate results
        unique_results = {}
        for result in search_results:
            if result.url not in unique_results and result.url != original_url:
                unique_results[result.url] = result
        
        # 4. Compile sources
        sources = [
            {
                "url": original_url,
                "title": title,
                "snippet": summary[:200],
                "type": "original",
            }
        ]
        
        for result in unique_results.values():
            sources.append({
                "url": result.url,
                "title": result.title,
                "snippet": result.snippet,
                "type": "corroboration",
            })
            
        # Add custom sources
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
            await source_store.mark_processed(custom_source.id)
        
        # 5. Verify & Extract Facts
        source_count = len(sources)
        verified = source_count >= 2
        
        facts = [
            {
                "claim": f"Story about: {title}",
                "source": original_url,
                "verified": verified,
            }
        ]
        
        if entities["people"]:
            facts.append({
                "claim": f"Involves: {', '.join(entities['people'][:3])}",
                "source": original_url,
                "verified": True,
            })

        # Answer human prompts (Phase 2)
        prompt_responses = []
        if human_prompts:
            for prompt in human_prompts:
                answer = await self._answer_prompt(
                    prompt.prompt_text,
                    context={
                        "title": title,
                        "summary": summary,
                        "sources": sources,
                        "facts": facts,
                        "entities": entities,
                        "historical_context": historical_context
                    }
                )
                await human_prompt_store.mark_answered(
                    prompt.id,
                    {
                        "answer": answer,
                        "sources_consulted": [s.get("url") or s.get("title") for s in sources[:5]],
                    }
                )
                prompt_responses.append({
                    "prompt_id": prompt.id,
                    "question": prompt.prompt_text,
                    "answer": answer,
                })

        await self.log_event(
            task.story_id,
            "research.completed",
            {
                "fact_count": len(facts),
                "source_count": len(sources),
                "verified": verified,
                "historical_context_count": len(historical_context)
            },
        )
        
        return {
            "facts": facts,
            "sources": sources,
            "entities": entities,
            "verified": verified,
            "source_count": len(sources),
            "prompt_responses": prompt_responses,
            "historical_context": historical_context
        }

    async def _answer_prompt(self, question: str, context: dict[str, Any]) -> str:
        """Answer a human prompt using research context."""
        sources_text = "\n".join([
            f"- {s.get('title', 'Untitled')}: {s.get('snippet', s.get('full_content', 'No content'))[:150]}"
            for s in context["sources"][:5]
        ])
        
        context_text = ""
        if context.get("historical_context"):
            context_text = "\nHistorical Context:\n" + "\n".join([
                f"- {h['content'][:150]}..." for h in context["historical_context"][:2]
            ])
        
        prompt = f"""You are a research assistant.
Story: {context['title']}
Context: {context['summary']}

Question: {question}

Sources:
{sources_text}
{context_text}

Answer the question based on findings.
"""
        try:
            return await self.chat_service.generate(
                system="You are a helpful research assistant.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
        except Exception:
            return "Unable to answer."

    async def draft(self, task: Task) -> dict[str, Any]:
        """Draft an article."""
        detection_data = task.input.get("detection_data", {})
        research_data = task.input.get("research_data", {})
        
        logger.info(
            "Drafting article",
            story_id=str(task.story_id),
            title=detection_data.get("title"),
        )
        
        sources = research_data.get("sources", [])
        entities = research_data.get("entities", {})
        facts = research_data.get("facts", [])
        verified = research_data.get("verified", False)
        historical_context = research_data.get("historical_context", [])
        
        # Build context string
        context_section = ""
        if historical_context:
            context_section = "\nHistorical Context/Related Stories:\n" + "\n".join([
                f"- {item['content']}" for item in historical_context
            ])
        
        prompt = f"""Title: {detection_data.get('title')}
Original Summary: {detection_data.get('summary')}
Source URL: {detection_data.get('url')}

Research Findings:
- Verified: {verified}
- Number of independent sources: {len(sources)}
- People: {', '.join(entities.get('people', [])[:5]) or 'None'}
- Orgs: {', '.join(entities.get('organizations', [])[:5]) or 'None'}

Key facts:
{chr(10).join(f"- {fact['claim']}" for fact in facts[:5])}

Additional sources:
{chr(10).join(f"- {s['title']}: {s['snippet'][:100]}..." for s in sources[1:4])}
{context_section}

Write a clear, factual news article (200-400 words).
Include a headline and article body.
Cite sources appropriately.
If historical context is provided, mention it to add depth (e.g., "This follows...").
"""
        
        try:
            article_text = await self.chat_service.generate(
                system="You are a reporter writing a news article.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            
            await self.log_event(
                task.story_id,
                "draft.completed",
                {
                    "word_count": len(article_text.split()),
                    "provider": self.chat_service.provider,
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

    async def revise(self, task: Task) -> dict[str, Any]:
        """Revise an article based on editor feedback."""
        draft = task.input.get("draft", {})
        feedback = task.input.get("feedback", "")
        original_article = draft.get("article", "")
        headline = draft.get("headline", "")
        
        logger.info(
            "Revising article",
            story_id=str(task.story_id),
            headline=headline,
        )
        
        prompt = f"""Original Article:
{original_article}

Editor's Feedback:
{feedback}

Rewrite the article to address the feedback.
Keep the same general structure unless requested otherwise.
"""
        
        try:
            revised_text = await self.chat_service.generate(
                system="You are a reporter modifying an article based on feedback.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            
            await self.log_event(
                task.story_id,
                "revision.completed",
                {
                    "word_count": len(revised_text.split()),
                    "provider": self.chat_service.provider,
                },
            )
            
            return {
                "article": revised_text,
                "headline": headline,
                "word_count": len(revised_text.split()),
                "is_revision": True
            }
            
        except Exception as e:
            logger.error("Revision failed", error=str(e))
            raise
