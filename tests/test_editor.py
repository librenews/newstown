import pytest
import json
from unittest.mock import AsyncMock, patch
from agents.editor import EditorAgent
from db import Task, TaskStage
from uuid import uuid4

@pytest.fixture
def editor():
    return EditorAgent()

@pytest.mark.asyncio
async def test_editor_score_logic(editor):
    analysis = {"score": 0.8, "style_issues": []}
    verification = {"claims_checked": 5, "verified_count": 4}
    
    score, v_score, s_score = editor._calculate_score(analysis, verification)
    
    assert s_score == 0.8
    assert v_score == 0.8 # 4/5
    # (0.8 * 0.6) + (0.8 * 0.4) = 0.48 + 0.32 = 0.8
    assert score == 0.8

@pytest.mark.asyncio
async def test_editor_decision_logic(editor):
    # Case 1: High scores -> Approve
    task = Task(
        id=uuid4(),
        story_id=uuid4(),
        stage=TaskStage.REVIEW,
        input={"draft": {"article": "Test draft", "headline": "Test"}}
    )
    
    with patch.object(editor, "_analyze_text", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = {"score": 0.9, "claims": ["c1"]}
        with patch.object(editor, "_verify_claims", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"claims_checked": 1, "verified_count": 1, "details": {}}
            with patch.object(editor, "heartbeat", new_callable=AsyncMock), \
                 patch.object(editor, "log_event", new_callable=AsyncMock), \
                 patch("agents.base.task_queue.complete", new_callable=AsyncMock):
                
                result = await editor.process_task(task)
                # Note: process_task returns None, the output is sent to task_queue.complete
                # But we can check if it completed successfully
                assert editor.success_count == 1

    # Case 2: Low verification -> Reject
    with patch.object(editor, "_analyze_text", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = {"score": 0.9, "claims": ["c1"]}
        with patch.object(editor, "_verify_claims", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"claims_checked": 5, "verified_count": 1, "details": {}}
            
            result = await editor.review_article(task)
            assert result["decision"] == "REJECT"

@pytest.mark.asyncio
async def test_compile_feedback(editor):
    analysis = {"score": 0.7, "style_issues": ["Too wordy"]}
    verification = {
        "claims_checked": 1, 
        "verified_count": 0, 
        "details": {"Claim 1": {"supported": False, "reason": "No evidence"}}
    }
    
    feedback = editor._compile_feedback(analysis, verification, 0.5, "REJECT")
    assert "REJECT" in feedback
    assert "Too wordy" in feedback
    assert "Claim 1" in feedback
    assert "No evidence" in feedback
