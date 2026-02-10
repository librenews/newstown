import pytest
import unittest.mock as mock
from uuid import uuid4
from db.articles import Article
from publishing.bluesky import BlueskyPublisher
from publishing import PublishResult

@pytest.mark.asyncio
async def test_bluesky_publisher_logic():
    # Mock settings
    with mock.patch("publishing.bluesky.settings") as mock_settings:
        mock_settings.bluesky_handle = "test.bsky.social"
        mock_settings.bluesky_app_password = "test-password"
        
        publisher = BlueskyPublisher()
        
        # Create a dummy article
        article = Article(
            id=uuid4(),
            story_id=uuid4(),
            headline="Test Headline",
            body="Test Body",
            metadata={"url": "https://example.com/article"}
        )
        
        # Mock the AT Protocol client
        with mock.patch("publishing.bluesky.Client") as MockClient:
            mock_client_instance = MockClient.return_value
            mock_client_instance.send_post.return_value = mock.Mock(
                uri="at://did:plc:123/app.bsky.feed.post/456",
                cid="abc"
            )
            
            # Mock publication_store.create
            with mock.patch("publishing.bluesky.publication_store.create", return_value=uuid4()) as mock_create:
                
                result = await publisher.publish(article)
                
                assert result.success is True
                assert result.metadata["uri"] == "at://did:plc:123/app.bsky.feed.post/456"
                mock_client_instance.login.assert_called_once_with("test.bsky.social", "test-password")
                mock_create.assert_called_once()
                
@pytest.mark.asyncio
async def test_bluesky_retract_logic():
    # Mock settings
    with mock.patch("publishing.bluesky.settings") as mock_settings:
        mock_settings.bluesky_handle = "test.bsky.social"
        mock_settings.bluesky_app_password = "test-password"
        
        publisher = BlueskyPublisher()
        
        from db.publications import Publication
        from datetime import datetime
        
        publication = Publication(
            id=uuid4(),
            article_id=uuid4(),
            channel="bluesky",
            published_at=datetime.now(),
            metadata={"uri": "at://did:plc:123/app.bsky.feed.post/456"}
        )
        
        # Mock the AT Protocol client
        with mock.patch("publishing.bluesky.Client") as MockClient:
            mock_client_instance = MockClient.return_value
            
            # Mock publication_store.retract
            with mock.patch("publishing.bluesky.publication_store.retract", return_value=True) as mock_retract:
                
                success = await publisher.retract(publication)
                
                assert success is True
                mock_client_instance.delete_post.assert_called_once_with("at://did:plc:123/app.bsky.feed.post/456")
                mock_retract.assert_called_once()
