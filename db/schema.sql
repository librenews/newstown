-- News Town Database Schema
-- Event-sourced newsroom with persistent task queue

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================================
-- EVENTS (Append-Only Ledger)
-- ============================================================================

CREATE TABLE IF NOT EXISTS story_events (
  id BIGSERIAL PRIMARY KEY,
  story_id UUID NOT NULL,
  agent_id UUID,
  event_type TEXT NOT NULL,
  data JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_story ON story_events(story_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON story_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON story_events(created_at DESC);

COMMENT ON TABLE story_events IS 'Immutable event log - single source of truth';
COMMENT ON COLUMN story_events.event_type IS 'Event types: story.detected, task.created, fact.added, story.published, etc.';


-- ============================================================================
-- TASKS (Work Queue)
-- ============================================================================

CREATE TABLE IF NOT EXISTS story_tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  story_id UUID NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  priority INTEGER DEFAULT 5,
  assigned_agent UUID,
  input JSONB DEFAULT '{}',
  output JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  deadline TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON story_tasks(status, priority DESC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON story_tasks(assigned_agent);
CREATE INDEX IF NOT EXISTS idx_tasks_story ON story_tasks(story_id);

COMMENT ON TABLE story_tasks IS 'Work queue - agents poll for pending tasks';
COMMENT ON COLUMN story_tasks.stage IS 'Pipeline stages: research, draft, edit, review, publish';
COMMENT ON COLUMN story_tasks.status IS 'Status: pending, active, completed, failed';


-- ============================================================================
-- AGENTS (Worker Registry)
-- ============================================================================

CREATE TABLE IF NOT EXISTS agents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  role TEXT NOT NULL,
  status TEXT DEFAULT 'idle',
  reliability_score FLOAT DEFAULT 1.0,
  task_count INTEGER DEFAULT 0,
  success_count INTEGER DEFAULT 0,
  last_heartbeat TIMESTAMPTZ,
  metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_agents_role ON agents(role, status);
CREATE INDEX IF NOT EXISTS idx_agents_heartbeat ON agents(last_heartbeat);

COMMENT ON TABLE agents IS 'Agent registry with reliability tracking';
COMMENT ON COLUMN agents.role IS 'Roles: chief, scout, reporter, editor, publisher';
COMMENT ON COLUMN agents.status IS 'Status: idle, working, offline';


-- ============================================================================
-- STORY MEMORY (Vectors + Facts)
-- ============================================================================

CREATE TABLE IF NOT EXISTS story_memory (
  id BIGSERIAL PRIMARY KEY,
  story_id UUID NOT NULL,
  content TEXT NOT NULL,
  embedding vector(1536),
  memory_type TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_story ON story_memory(story_id);
CREATE INDEX IF NOT EXISTS idx_memory_type ON story_memory(memory_type);
CREATE INDEX IF NOT EXISTS idx_memory_embedding ON story_memory USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

COMMENT ON TABLE story_memory IS 'Story facts and embeddings for semantic search';
COMMENT ON COLUMN story_memory.memory_type IS 'Types: fact, quote, source, summary';


-- ============================================================================
-- MATERIALIZED VIEW: Stories
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS stories;

CREATE MATERIALIZED VIEW stories AS
SELECT 
  story_id,
  MIN(created_at) as first_seen,
  MAX(created_at) as last_updated,
  COUNT(*) as event_count,
  (
    SELECT event_type 
    FROM story_events e 
    WHERE e.story_id = s.story_id 
    ORDER BY created_at DESC 
    LIMIT 1
  ) as current_stage,
  (
    SELECT data 
    FROM story_events e 
    WHERE e.story_id = s.story_id AND e.event_type = 'story.detected'
    ORDER BY created_at ASC 
    LIMIT 1
  ) as detection_data
FROM story_events s
GROUP BY story_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stories_id ON stories(story_id);
CREATE INDEX IF NOT EXISTS idx_stories_updated ON stories(last_updated DESC);

COMMENT ON MATERIALIZED VIEW stories IS 'Story state reconstructed from events - refresh periodically';


-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to refresh stories view
CREATE OR REPLACE FUNCTION refresh_stories()
RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY stories;
END;
$$ LANGUAGE plpgsql;

-- Function to create event
CREATE OR REPLACE FUNCTION create_event(
  p_story_id UUID,
  p_agent_id UUID,
  p_event_type TEXT,
  p_data JSONB
)
RETURNS BIGINT AS $$
DECLARE
  event_id BIGINT;
BEGIN
  INSERT INTO story_events (story_id, agent_id, event_type, data)
  VALUES (p_story_id, p_agent_id, p_event_type, p_data)
  RETURNING id INTO event_id;
  
  RETURN event_id;
END;
$$ LANGUAGE plpgsql;

-- Function to claim a task (atomic)
CREATE OR REPLACE FUNCTION claim_task(
  p_agent_id UUID,
  p_role TEXT
)
RETURNS TABLE (
  task_id UUID,
  story_id UUID,
  stage TEXT,
  input JSONB
) AS $$
DECLARE
  claimed_task RECORD;
BEGIN
  -- Find and claim highest priority pending task for this role
  UPDATE story_tasks st
  SET 
    status = 'active',
    assigned_agent = p_agent_id,
    started_at = now()
  FROM (
    SELECT st2.id
    FROM story_tasks st2
    WHERE st2.status = 'pending'
      AND st2.stage IN (
        SELECT UNNEST(CASE p_role
          WHEN 'scout' THEN ARRAY['detect']
          WHEN 'reporter' THEN ARRAY['research', 'draft']
          WHEN 'editor' THEN ARRAY['edit', 'review']
          WHEN 'publisher' THEN ARRAY['publish']
          ELSE ARRAY[]::TEXT[]
        END)
      )
    ORDER BY st2.priority DESC, st2.created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  ) subquery
  WHERE st.id = subquery.id
  RETURNING st.id, st.story_id, st.stage, st.input
  INTO claimed_task;
  
  IF claimed_task IS NOT NULL THEN
    RETURN QUERY SELECT 
      claimed_task.id,
      claimed_task.story_id,
      claimed_task.stage,
      claimed_task.input;
  END IF;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- HUMAN OVERSIGHT (Phase 2)
-- ============================================================================

-- Human prompts/questions for agents
CREATE TABLE IF NOT EXISTS human_prompts (
  id SERIAL PRIMARY KEY,
  story_id UUID NOT NULL,
  prompt_text TEXT NOT NULL,
  context JSONB DEFAULT '{}',
  created_by VARCHAR(255),
  created_at TIMESTAMPTZ DEFAULT now(),
  status VARCHAR(50) DEFAULT 'pending',
  response JSONB
);

CREATE INDEX IF NOT EXISTS idx_human_prompts_story ON human_prompts(story_id);
CREATE INDEX IF NOT EXISTS idx_human_prompts_status ON human_prompts(status);
CREATE INDEX IF NOT EXISTS idx_human_prompts_created ON human_prompts(created_at DESC);

COMMENT ON TABLE human_prompts IS 'Human questions/instructions for agents';
COMMENT ON COLUMN human_prompts.status IS 'Status: pending, processing, answered';

-- Human-provided sources
CREATE TABLE IF NOT EXISTS story_sources (
  id SERIAL PRIMARY KEY,
  story_id UUID NOT NULL,
  source_type VARCHAR(50) NOT NULL,
  source_url TEXT,
  source_content TEXT,
  source_metadata JSONB DEFAULT '{}',
  added_by VARCHAR(255),
  added_at TIMESTAMPTZ DEFAULT now(),
  processed BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_story_sources_story ON story_sources(story_id);
CREATE INDEX IF NOT EXISTS idx_story_sources_processed ON story_sources(processed);
CREATE INDEX IF NOT EXISTS idx_story_sources_added ON story_sources(added_at DESC);

COMMENT ON TABLE story_sources IS 'Human-added supplementary sources';
COMMENT ON COLUMN story_sources.source_type IS 'Types: url, document, text';

-- Published articles
CREATE TABLE IF NOT EXISTS articles (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  story_id UUID NOT NULL,
  headline TEXT NOT NULL,
  byline TEXT,
  summary TEXT,
  body TEXT,
  sources JSONB DEFAULT '[]',
  entities JSONB DEFAULT '[]',
  tags TEXT[],
  metadata JSONB DEFAULT '{}',
  published_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_articles_story ON articles(story_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_tags ON articles USING gin(tags);

COMMENT ON TABLE articles IS 'Published articles in structured format';
COMMENT ON COLUMN articles.body IS 'Article body in Markdown format';
COMMENT ON COLUMN articles.sources IS 'Array of source objects: {url, title, accessed_at}';

-- ============================================================================
-- PHASE 3: Publishing & Distribution
-- ============================================================================

-- Publications: Record of articles published to various channels
CREATE TABLE IF NOT EXISTS publications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    channel VARCHAR(50) NOT NULL,  -- 'rss', 'email', 'twitter', etc
    status VARCHAR(20) DEFAULT 'published',  -- 'published', 'retracted'
    published_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    retracted_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_publications_article ON publications(article_id);
CREATE INDEX IF NOT EXISTS idx_publications_channel ON publications(channel);
CREATE INDEX IF NOT EXISTS idx_publications_status ON publications(status);
CREATE INDEX IF NOT EXISTS idx_publications_published_at ON publications(published_at DESC);

-- Publishing Schedule: Queue for scheduled publications
CREATE TABLE IF NOT EXISTS publishing_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    channels TEXT[] NOT NULL, -- ['rss', 'email', 'twitter']
    scheduled_for TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'published', 'cancelled', 'failed'
    published_at TIMESTAMPTZ,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_schedule_article ON publishing_schedule(article_id);
CREATE INDEX IF NOT EXISTS idx_schedule_status ON publishing_schedule(status);
CREATE INDEX IF NOT EXISTS idx_schedule_scheduled_for ON publishing_schedule(scheduled_for);

-- ============================================================================
-- PHASE 3: Governance & Safety
-- ============================================================================

-- Governance Rules: Publishing rules and policies
CREATE TABLE IF NOT EXISTS governance_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_type VARCHAR(50) NOT NULL, -- 'source_count', 'approval_required', 'topic_restriction', 'moderation'
    name VARCHAR(200) NOT NULL,
    description TEXT,
    condition JSONB NOT NULL, -- rule parameters {"min_sources": 2}
    action VARCHAR(50) NOT NULL, -- 'block', 'require_approval', 'flag', 'warn'
    priority INTEGER DEFAULT 0, -- higher = evaluated first
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_governance_rules_enabled ON governance_rules(enabled, priority DESC);
CREATE INDEX IF NOT EXISTS idx_governance_rules_type ON governance_rules(rule_type);

-- Approval Requests: Human approval queue
CREATE TABLE IF NOT EXISTS approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    reason TEXT NOT NULL, -- why approval needed
    rule_violations JSONB, -- [{rule_id, rule_name, violation_details}]
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    auto_approved BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_article ON approval_requests(article_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON approval_requests(status);
CREATE INDEX IF NOT EXISTS idx_approval_requests_requested_at ON approval_requests(requested_at DESC);

-- Audit Log: All governance and publishing decisions
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL, -- 'article.published', 'article.retracted', 'approval.granted', 'rule.triggered'
    entity_type VARCHAR(50), -- 'article', 'publication', 'agent', 'rule'
    entity_id UUID,
    details JSONB NOT NULL, -- event-specific data
    user_id VARCHAR(100), -- who triggered (agent or human)
    severity VARCHAR(20) DEFAULT 'info', -- 'info', 'warning', 'error', 'critical'
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);

