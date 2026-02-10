import pytest
from agents.reporter import ReporterAgent
from agents.editor import EditorAgent
from db import Task, TaskStage
from uuid import uuid4

@pytest.mark.asyncio
async def test_reporter_two_phase_research():
    """Verify Reporter performs entity refinement and discovery queries."""
    agent = ReporterAgent()
    task = Task(
        id=uuid4(),
        story_id=uuid4(),
        stage=TaskStage.RESEARCH,
        priority=5,
        input_data={
            "detection_data": {
                "title": "Apple announces revolutionary new device",
                "summary": "Apple CEO Tim Cook unveiled a new headset today in Cupertino.",
                "url": "https://techcrunch.com/apple-device"
            }
        }
    )
    
    result = await agent.research(task)
    
    # Check entities refined by LLM logic (mocked or real)
    assert "entities" in result
    assert "people" in result["entities"]
    
    # Check deep dive questions
    assert "investigative_leads" in result
    assert len(result["investigative_leads"]) >= 2

@pytest.mark.asyncio
async def test_editor_source_diversity():
    """Verify Editor penalizes low source diversity."""
    agent = EditorAgent()
    
    # Low diversity: only one corroborating domain
    sources_low = [
        {"url": "https://source1.com/a", "type": "original"},
        {"url": "https://source1.com/b", "type": "corroboration"}
    ]
    assert agent._check_source_diversity(sources_low) == 0.0
    
    # High diversity: multiple domains
    sources_high = [
        {"url": "https://news.com/a", "type": "original"},
        {"url": "https://reuters.com/b", "type": "corroboration"},
        {"url": "https://ap.org/c", "type": "corroboration"}
    ]
    assert agent._check_source_diversity(sources_high) == 1.0
