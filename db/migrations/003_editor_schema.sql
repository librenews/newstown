CREATE TABLE IF NOT EXISTS article_reviews (
    id BIGSERIAL PRIMARY KEY,
    article_id UUID NOT NULL REFERENCES articles(id),
    editor_agent_id UUID NOT NULL,
    score FLOAT NOT NULL,
    feedback TEXT NOT NULL,
    decision VARCHAR(50) NOT NULL CHECK (decision IN ('APPROVE', 'REJECT')),
    meta JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_reviews_article_id ON article_reviews(article_id);
CREATE INDEX idx_reviews_decision ON article_reviews(decision);
