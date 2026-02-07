# News Town - Docker Deployment Guide

## Quick Start

### 1. Set Up Environment

Create a `.env` file with your API keys:

```bash
# Required
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional but recommended
BRAVE_API_KEY=BSA...

# Database password (optional, defaults to newstown_dev)
DB_PASSWORD=your_secure_password

# Optional configuration
LOG_LEVEL=INFO
ENVIRONMENT=production
MIN_NEWSWORTHINESS_SCORE=0.6
MAX_STORIES_PER_DAY=20
```

### 2. Build and Start

```bash
# Build and start all services
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

That's it! News Town will:
- Start PostgreSQL with pgvector extension
- Run database migrations automatically
- Start the Chief, Scouts, and Reporters
- Begin monitoring feeds and generating stories

### 3. Monitor

```bash
# View logs
docker-compose logs -f app

# View database logs
docker-compose logs -f db

# Check status
docker-compose ps
```

### 4. Stop

```bash
# Stop services
docker-compose down

# Stop and remove volumes (deletes all data)
docker-compose down -v
```

---

## Production Deployment

### Docker Compose (Recommended for single server)

1. **Clone repository on server:**
   ```bash
   git clone <your-repo>
   cd newstown
   ```

2. **Create production .env file:**
   ```bash
   cp .env.example .env
   # Edit .env with production values
   ```

3. **Start with production settings:**
   ```bash
   docker-compose up -d
   ```

4. **Configure auto-restart:**
   The compose file already includes `restart: unless-stopped`

5. **Set up log rotation:**
   ```bash
   # Configure Docker log rotation
   # Edit /etc/docker/daemon.json
   {
     "log-driver": "json-file",
     "log-opts": {
       "max-size": "10m",
       "max-file": "3"
     }
   }
   ```

### Kubernetes (For scaling)

<details>
<summary>Basic Kubernetes manifests (expand for examples)</summary>

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: newstown
spec:
  replicas: 1
  selector:
    matchLabels:
      app: newstown
  template:
    metadata:
      labels:
        app: newstown
    spec:
      containers:
      - name: newstown
        image: your-registry/newstown:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: newstown-secrets
              key: database-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: newstown-secrets
              key: openai-key
        # ... other env vars
```

</details>

---

## Database Access

### Connect to PostgreSQL

```bash
# Via docker-compose
docker-compose exec db psql -U newstown -d newstown

# Directly (if port is exposed)
psql -h localhost -U newstown -d newstown
```

### Useful Queries

```sql
-- See recent stories
SELECT story_id, data->>'title', created_at 
FROM story_events 
WHERE event_type = 'story.detected' 
ORDER BY created_at DESC 
LIMIT 10;

-- Check agent health
SELECT role, status, last_heartbeat 
FROM agents 
ORDER BY last_heartbeat DESC;

-- View active tasks
SELECT stage, status, priority, created_at 
FROM story_tasks 
WHERE status = 'pending' 
ORDER BY priority DESC;
```

---

## Scaling

### Horizontal Scaling (Multiple Reporters)

Edit `docker-compose.yml` to scale reporter agents:

```yaml
services:
  app:
    # ... existing config ...
    deploy:
      replicas: 3  # Run 3 instances
```

Or use docker-compose scale:
```bash
docker-compose up -d --scale app=3
```

**Note:** Currently all agents run in the same process. For true horizontal scaling, you'd need to split agents into separate services.

### Vertical Scaling (More Resources)

```yaml
services:
  app:
    # ... existing config ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

---

## Backups

### Automated Database Backups

```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T db pg_dump -U newstown newstown | gzip > "$BACKUP_DIR/newstown_$TIMESTAMP.sql.gz"
# Keep only last 7 days
find $BACKUP_DIR -name "newstown_*.sql.gz" -mtime +7 -delete
EOF

chmod +x backup.sh

# Add to cron (daily at 2am)
0 2 * * * /path/to/newstown/backup.sh
```

### Restore from Backup

```bash
# Stop app (keep db running)
docker-compose stop app

# Restore
gunzip < backup.sql.gz | docker-compose exec -T db psql -U newstown newstown

# Restart
docker-compose start app
```

---

## Monitoring

### Health Checks

The PostgreSQL service has a built-in health check. The app will only start after the database is healthy.

### Prometheus Metrics (Future)

To add metrics:
1. Add prometheus client to requirements.txt
2. Expose metrics endpoint in main.py
3. Add Prometheus to docker-compose.yml

### Log Aggregation

For production, consider sending logs to:
- **ELK Stack** (Elasticsearch, Logstash, Kibana)
- **Loki** (Grafana Loki)
- **CloudWatch** (AWS)
- **Stackdriver** (GCP)

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs app

# Check if DB is ready
docker-compose exec db pg_isready -U newstown

# Rebuild without cache
docker-compose build --no-cache
docker-compose up -d
```

### Database connection issues

```bash
# Verify DATABASE_URL
docker-compose exec app env | grep DATABASE_URL

# Test connection manually
docker-compose exec app python -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('postgresql://newstown:password@db:5432/newstown'))"
```

### Out of memory

```bash
# Check resource usage
docker stats

# Increase Docker memory limit (Docker Desktop)
# Preferences > Resources > Memory
```

### spaCy model not found

The Dockerfile downloads the model during build. If it's missing:

```bash
# Rebuild image
docker-compose build --no-cache app
docker-compose up -d
```

---

## Environment Variables

All configuration is via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key |
| `BRAVE_API_KEY` | No | - | Brave Search API key |
| `LOG_LEVEL` | No | INFO | DEBUG, INFO, WARNING, ERROR |
| `ENVIRONMENT` | No | production | development, production |
| `MIN_NEWSWORTHINESS_SCORE` | No | 0.6 | Story detection threshold |
| `MAX_STORIES_PER_DAY` | No | 20 | Rate limit |

See `.env.example` for complete list.

---

## Security Considerations

### Production Checklist

- [ ] Use strong `DB_PASSWORD`
- [ ] Store API keys in secrets manager (not .env file)
- [ ] Use HTTPS for any exposed endpoints
- [ ] Run as non-root user (already configured)
- [ ] Enable firewall (only expose necessary ports)
- [ ] Set up log monitoring for suspicious activity
- [ ] Regular security updates: `docker-compose pull && docker-compose up -d`
- [ ] Backup encryption for database dumps

### Network Security

The default setup uses a bridge network. For production:
- Don't expose PostgreSQL port (5432) to internet
- Use reverse proxy for any web interface
- Consider VPN for administration

---

## Updates

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Check if migrations are needed
docker-compose exec app python -m db.migrate
```

---

## Cost Estimation (AWS EC2 Example)

**Server:** t3.medium (2 vCPU, 4GB RAM)
- ~$30/month

**Storage:** 20GB EBS
- ~$2/month

**API Costs:** (varies by usage)
- Anthropic Claude: ~$0.01 per article
- Brave Search: Free tier → $5/month
- OpenAI (if used): ~$0.002 per article

**Total:** ~$40-60/month for moderate usage

---

## Next Steps

1. Add publishing pipeline (output to files/CMS)
2. Create web dashboard for monitoring
3. Add health check endpoint
4. Implement graceful shutdown
5. Add Prometheus metrics
6. Create Kubernetes manifests for scaling
