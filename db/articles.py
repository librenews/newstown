"""Article storage and publishing."""
import json
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from db.connection import db
from config.logging import get_logger

logger = get_logger(__name__)


class Article(BaseModel):
    """Published article."""
    id: UUID
    story_id: UUID
    headline: str
    byline: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None  # Markdown format
    sources: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    published_at: datetime
    updated_at: datetime


class ArticleReview(BaseModel):
    """Editor review of an article."""
    id: int
    article_id: UUID
    editor_agent_id: UUID
    score: float
    feedback: str
    decision: str
    meta: dict[str, Any] = {}
    created_at: datetime


class ArticleStore:
    """Manage published articles."""
    
    async def record_review(
        self,
        article_id: UUID,
        editor_agent_id: UUID,
        score: float,
        feedback: str,
        decision: str,
        meta: Optional[dict] = None,
    ) -> int:
        """Record an editor review."""
        review_id = await db.fetchval(
            """
            INSERT INTO article_reviews (
                article_id, editor_agent_id, score, feedback, decision, meta
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            article_id,
            editor_agent_id,
            score,
            feedback,
            decision,
            json.dumps(meta or {}),
        )
        
        logger.info(
            "Article review recorded",
            article_id=str(article_id),
            decision=decision,
            score=score,
        )
        
        return review_id

    async def get_article_reviews(self, article_id: UUID) -> list[ArticleReview]:
        """Get reviews for an article."""
        rows = await db.fetch(
            """
            SELECT * FROM article_reviews
            WHERE article_id = $1
            ORDER BY created_at DESC
            """,
            article_id,
        )
        
        reviews = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict['meta'], str):
                row_dict['meta'] = json.loads(row_dict['meta'])
            reviews.append(ArticleReview(**row_dict))
            
        return reviews
    
    async def create_article(
        self,
        story_id: UUID,
        headline: str,
        body: str,
        byline: Optional[str] = None,
        summary: Optional[str] = None,
        sources: Optional[list[dict]] = None,
        entities: Optional[list[dict]] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> UUID:
        """Create a new published article."""
        article_id = await db.fetchval(
            """
            INSERT INTO articles (
                story_id, headline, byline, summary, body,
                sources, entities, tags, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            story_id,
            headline,
            byline,
            summary,
            body,
            json.dumps(sources or []),
            json.dumps(entities or []),
            tags or [],
            json.dumps(metadata or {}),
        )
        
        logger.info(
            "Article published",
            article_id=str(article_id),
            story_id=str(story_id),
            headline=headline,
        )
        
        return article_id
    
    async def get_article(self, article_id: UUID) -> Optional[Article]:
        """Get an article by ID."""
        row = await db.fetchrow(
            "SELECT * FROM articles WHERE id = $1",
            article_id,
        )
        
        if not row:
            return None
        
        row_dict = dict(row)
        # Deserialize JSON fields
        if isinstance(row_dict['sources'], str):
            row_dict['sources'] = json.loads(row_dict['sources'])
        if isinstance(row_dict['entities'], str):
            row_dict['entities'] = json.loads(row_dict['entities'])
        if isinstance(row_dict['metadata'], str):
            row_dict['metadata'] = json.loads(row_dict['metadata'])
        
        return Article(**row_dict)
    
    async def get_story_article(self, story_id: UUID) -> Optional[Article]:
        """Get the latest article for a story."""
        row = await db.fetchrow(
            """
            SELECT * FROM articles
            WHERE story_id = $1
            ORDER BY published_at DESC
            LIMIT 1
            """,
            story_id,
        )
        
        if not row:
            return None
        
        row_dict = dict(row)
        if isinstance(row_dict['sources'], str):
            row_dict['sources'] = json.loads(row_dict['sources'])
        if isinstance(row_dict['entities'], str):
            row_dict['entities'] = json.loads(row_dict['entities'])
        if isinstance(row_dict['metadata'], str):
            row_dict['metadata'] = json.loads(row_dict['metadata'])
        
        return Article(**row_dict)
    
    async def list_recent_articles(self, limit: int = 20) -> list[Article]:
        """Get recently published articles."""
        rows = await db.fetch(
            """
            SELECT * FROM articles
            ORDER BY published_at DESC
            LIMIT $1
            """,
            limit,
        )
        
        articles = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict['sources'], str):
                row_dict['sources'] = json.loads(row_dict['sources'])
            if isinstance(row_dict['entities'], str):
                row_dict['entities'] = json.loads(row_dict['entities'])
            if isinstance(row_dict['metadata'], str):
                row_dict['metadata'] = json.loads(row_dict['metadata'])
            articles.append(Article(**row_dict))
        
        return articles
    
    async def update_article(
        self,
        article_id: UUID,
        **updates,
    ) -> None:
        """Update an article."""
        # Build dynamic update query
        set_clauses = []
        values = []
        param_num = 1
        
        for field, value in updates.items():
            if field in ['sources', 'entities', 'metadata'] and isinstance(value, (dict, list)):
                value = json.dumps(value)
            set_clauses.append(f"{field} = ${param_num}")
            values.append(value)
            param_num += 1
        
        if not set_clauses:
            return
        
        # Add updated_at
        set_clauses.append(f"updated_at = ${param_num}")
        values.append(datetime.now())
        param_num += 1
        
        # Add article_id
        values.append(article_id)
        
        query = f"""
            UPDATE articles
            SET {', '.join(set_clauses)}
            WHERE id = ${param_num}
        """
        
        await db.execute(query, *values)
        logger.info("Article updated", article_id=str(article_id))
    
    def render_html(self, article: Article) -> str:
        """Render article as HTML."""
        try:
            import markdown
            
            html_body = markdown.markdown(article.body or "", extensions=['extra', 'codehilite'])
            
            html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{article.headline}</title>
    <style>
        body {{ font-family: Georgia, serif; max-width: 700px; margin: 0 auto; padding: 20px; }}
        h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .byline {{ color: #666; margin-bottom: 20px; }}
        .summary {{ font-size: 1.2em; margin-bottom: 30px; color: #333; }}
        .body {{ line-height: 1.6; }}
        .sources {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 20px; }}
        .sources h3 {{ font-size: 1.2em; }}
        .sources ul {{ list-style: none; padding: 0; }}
        .sources li {{ margin-bottom: 10px; }}
    </style>
</head>
<body>
    <article>
        <h1>{article.headline}</h1>
        {f'<p class="byline">By {article.byline}</p>' if article.byline else ''}
        {f'<p class="summary">{article.summary}</p>' if article.summary else ''}
        <div class="body">
            {html_body}
        </div>
        {self._render_sources_html(article.sources) if article.sources else ''}
    </article>
</body>
</html>
            """
            return html
        except ImportError:
            logger.warning("markdown package not installed, returning plain HTML")
            return f"<h1>{article.headline}</h1><pre>{article.body}</pre>"
    
    def _render_sources_html(self, sources: list[dict]) -> str:
        """Render sources section as HTML."""
        if not sources:
            return ""
        
        items = []
        for source in sources:
            url = source.get('url', '')
            title = source.get('title', url)
            items.append(f'<li><a href="{url}">{title}</a></li>')
        
        return f"""
        <div class="sources">
            <h3>Sources</h3>
            <ul>
                {''.join(items)}
            </ul>
        </div>
        """
    
    def render_markdown(self, article: Article) -> str:
        """Render article as markdown."""
        lines = []
        lines.append(f"# {article.headline}")
        lines.append("")
        
        if article.byline:
            lines.append(f"*By {article.byline}*")
            lines.append("")
        
        if article.summary:
            lines.append(f"**{article.summary}**")
            lines.append("")
        
        if article.body:
            lines.append(article.body)
            lines.append("")
        
        if article.sources:
            lines.append("## Sources")
            lines.append("")
            for source in article.sources:
                title = source.get('title', source.get('url', 'Unknown'))
                url = source.get('url', '')
                lines.append(f"- [{title}]({url})")
        
        return "\n".join(lines)


# Global instance
article_store = ArticleStore()
