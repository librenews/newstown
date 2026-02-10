import pytest
import unittest.mock as mock
from uuid import uuid4
from db.tasks import Task, TaskStage
from agents.editor import EditorAgent

@pytest.mark.asyncio
async def test_editor_ap_style_analysis():
    """Test that the editor correctly identifies AP Style violations."""
    agent = EditorAgent()
    
    # Mock chat service
    with mock.patch.object(agent.chat_service, 'generate') as mock_gen:
        mock_gen.return_value = '{"claims": ["Fact 1"], "tone": "Biased", "ap_violations": ["Oxford comma used", "Lowercase title"], "style_issues": [], "grammar_issues": [], "score": 0.5}'
        
        analysis = await agent._analyze_text("Test article text.")
        
        assert "ap_violations" in analysis
        assert len(analysis["ap_violations"]) == 2
        assert analysis["tone"] == "Biased"

@pytest.mark.asyncio
async def test_editor_review_persistence():
    """Test that reviews are persisted to the database."""
    agent = EditorAgent()
    task = Task(
        id=uuid4(),
        story_id=uuid4(),
        stage=TaskStage.REVIEW,
        input={"draft": {"article": "Test text", "headline": "Test"}}
    )
    
    # Mock analyze, verify, and store
    with mock.patch.object(agent, '_analyze_text', return_value={"claims": [], "score": 0.9, "ap_violations": []}), \
         mock.patch.object(agent, '_verify_claims', return_value={"claims_checked": 0, "verified_count": 0, "details": {}}), \
         mock.patch("db.governance.article_review_store.create") as mock_create:
        
        mock_create.return_value = uuid4()
        
        result = await agent.review_article(task)
        
        assert result["decision"] == "APPROVE"
        mock_create.assert_called_once()
        # Verify the decision was persisted
        args, kwargs = mock_create.call_args
        assert kwargs["decision"] == "APPROVE"
        assert kwargs["score"] >= 0.8

@pytest.mark.asyncio
async def test_editor_rejection_criteria():
    """Test that the editor rejects articles with low scores or many variations."""
    agent = EditorAgent()
    
    # Low verification score
    analysis = {"score": 0.9, "ap_violations": []}
    verification = {"claims_checked": 5, "verified_count": 2} # 40% verification
    
    score, v_score, s_score = agent._calculate_score(analysis, verification)
    
    assert v_score < 0.9
    # Decision logic in review_article: decision = "APPROVE" if verification_score >= 0.9 and style_score >= 0.8 else "REJECT"
    assert v_score < 0.9
