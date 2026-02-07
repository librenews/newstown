"""Email newsletter publisher using SendGrid."""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from jinja2 import Template
from db.articles import Article
from db.publications import publication_store, Publication
from publishing import Publisher, PublishResult
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


class EmailProvider(ABC):
    """Abstract email provider interface (pluggable)."""
    
    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> bool:
        """Send a single email."""
        pass
    
    @abstractmethod
    async def send_batch(
        self,
        recipients: List[str],
        subject: str,
        html: str,
        text: str,
    ) -> Dict[str, bool]:
        """Send email to multiple recipients."""
        pass


class SendGridProvider(EmailProvider):
    """SendGrid email provider implementation."""
    
    def __init__(self, api_key: str):
        self.client = SendGridAPIClient(api_key)
    
    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> bool:
        """Send email via SendGrid."""
        try:
            message = Mail(
                from_email=Email(
                    settings.email_from_address,
                    settings.email_from_name,
                ),
                to_emails=To(to),
                subject=subject,
                plain_text_content=Content("text/plain", text),
                html_content=Content("text/html", html),
            )
            
            response = self.client.send(message)
            success = response.status_code in (200, 201, 202)
            
            if success:
                logger.info("Email sent", to=to, subject=subject)
            else:
                logger.warning(
                    "Email send failed",
                    to=to,
                    status=response.status_code,
                )
            
            return success
            
        except Exception as e:
            logger.error("SendGrid error", error=str(e), to=to)
            return False
    
    async def send_batch(
        self,
        recipients: List[str],
        subject: str,
        html: str,
        text: str,
    ) -> Dict[str, bool]:
        """Send to multiple recipients."""
        results = {}
        for recipient in recipients:
            results[recipient] = await self.send_email(
                recipient,
                subject,
                html,
                text,
            )
        return results


class EmailPublisher(Publisher):
    """Publish articles as email newsletters."""
    
    # Email HTML template
    HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 20px; }
        h1 { font-size: 28px; color: #333; }
        .byline { color: #666; font-size: 14px; margin-bottom: 20px; }
        .summary { font-size: 18px; font-weight: bold; margin: 20px 0; }
        .body { line-height: 1.6; color: #333; }
        .sources { margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }
        .sources h3 { font-size: 16px; }
        .sources ul { list-style: none; padding: 0; }
        .sources li { margin: 10px 0; }
        .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; 
                  font-size: 12px; color: #999; text-align: center; }
    </style>
</head>
<body>
    <h1>{{ headline }}</h1>
    {% if byline %}<p class="byline">By {{ byline }}</p>{% endif %}
    {% if summary %}<p class="summary">{{ summary }}</p>{% endif %}
    <div class="body">{{ body }}</div>
    {% if sources %}
    <div class="sources">
        <h3>Sources</h3>
        <ul>
        {% for source in sources %}
            <li><a href="{{ source.url }}">{{ source.title or source.url }}</a></li>
        {% endfor %}
        </ul>
    </div>
    {% endif %}
    <div class="footer">
        <p>News Town | Multi-agent news reporting</p>
    </div>
</body>
</html>
    """
    
    # Plain text template
    TEXT_TEMPLATE = """
{{ headline }}
{% if byline %}By {{ byline }}{% endif %}

{% if summary %}{{ summary }}

{% endif %}{{ body }}

{% if sources %}
Sources:
{% for source in sources %}
- {{ source.title or source.url }}: {{ source.url }}
{% endfor %}
{% endif %}

---
News Town | Multi-agent news reporting
    """
    
    def __init__(self, provider: Optional[EmailProvider] = None):
        # Use SendGrid by default if API key available
        if provider:
            self.provider = provider
        elif settings.sendgrid_api_key:
            self.provider = SendGridProvider(settings.sendgrid_api_key)
        else:
            raise ValueError("No email provider configured")
    
    @property
    def channel_name(self) -> str:
        return "email"
    
    async def publish(self, article: Article) -> PublishResult:
        """Publish article as email (not implemented - use send_to)."""
        raise NotImplementedError(
            "Use send_to() or send_batch() to send emails to specific recipients"
        )
    
    async def retract(self, publication: Publication) -> bool:
        """Cannot retract emails (already sent)."""
        # Mark as retracted in database
        return await publication_store.retract(
            publication.id,
            "Email cannot be recalled (already sent)"
        )
    
    async def send_to(
        self,
        article: Article,
        recipient: str,
    ) -> PublishResult:
        """Send article to a single recipient."""
        try:
            # Format email
            html = self._format_html(article)
            text = self._format_text(article)
            subject = article.headline
            
            # Send via provider
            success = await self.provider.send_email(
                to=recipient,
                subject=subject,
                html=html,
                text=text,
            )
            
            if not success:
                return PublishResult(
                    success=False,
                    error="Email send failed"
                )
            
            # Record publication
            pub_id = await publication_store.create(
                article_id=article.id,
                channel=self.channel_name,
                metadata={"recipient": recipient}
            )
            
            return PublishResult(
                success=True,
                publication_id=pub_id,
                metadata={"recipient": recipient}
            )
            
        except Exception as e:
            logger.error("Email publish failed", error=str(e))
            return PublishResult(success=False, error=str(e))
    
    async def send_batch(
        self,
        article: Article,
        recipients: List[str],
    ) -> Dict[str, PublishResult]:
        """Send article to multiple recipients."""
        results = {}
        for recipient in recipients:
            results[recipient] = await self.send_to(article, recipient)
        return results
    
    def _format_html(self, article: Article) -> str:
        """Format article as HTML email."""
        template = Template(self.HTML_TEMPLATE)
        return template.render(
            headline=article.headline,
            byline=article.byline,
            summary=article.summary,
            body=article.body,
            sources=article.sources or [],
        )
    
    def _format_text(self, article: Article) -> str:
        """Format article as plain text email."""
        template = Template(self.TEXT_TEMPLATE)
        return template.render(
            headline=article.headline,
            byline=article.byline,
            summary=article.summary,
            body=article.body,
            sources=article.sources or [],
        )


# Global instance (if SendGrid configured)
email_publisher = None
if settings.sendgrid_api_key:
    email_publisher = EmailPublisher()
