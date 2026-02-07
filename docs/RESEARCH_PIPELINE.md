# Research Pipeline Enhancement

## What Changed

The Reporter's research phase now includes:

### 1. **Web Search Integration** (Brave Search)
- Searches for corroborating sources using the story title
- Returns up to 5 additional sources
- Extensible design supports adding other search providers later

### 2. **Entity Extraction** (spaCy)
- Extracts people, organizations, and locations from story text
- Uses `en_core_web_sm` model
- Categorizes entities by type

### 3. **Multi-Source Verification**
- Counts total sources (original + search results)
- Flags stories as "verified" if they have 2+ sources
- Tracks source count in research output

### 4. **Enhanced Drafting**
- Claude receives full research context:
  - Verification status
  - Entity lists (people, orgs, locations)
  - Multiple source snippets
  - Key facts
- Prompts Claude to note unverified single-source stories

## How It Works

**Research Flow:**
```
1. Extract entities from feed summary
2. Search web for story title
3. Combine original + search results
4. Count sources (verify if >= 2)
5. Create fact list with entities
6. Pass to draft stage
```

**Multi-Source Verification (MVP):**
- **Basic**: Count sources, flag if only one
- **Future**: Compare claims across sources, check agreement, weight by credibility

## Setup

### 1. Install spaCy model:
```bash
python -m spacy download en_core_web_sm
```

### 2. Add Brave API key to `.env`:
```bash
BRAVE_API_KEY=BSA...
```

Get API key from: https://brave.com/search/api/

### 3. Optional: Add other search providers

The search system uses a plugin pattern. To add a new provider:

```python
# In ingestion/search.py
class GoogleSearchProvider(SearchProvider):
    async def search(self, query: str, num_results: int = 5):
        # Implementation here
        pass

# Register in SearchService.__init__
if settings.google_search_api_key:
    self.providers["google"] = GoogleSearchProvider(...)
```

## Example Research Output

**Before (stub):**
```json
{
  "facts": [{"claim": "Story detected", "verified": false}],
  "sources": ["https://example.com"],
  "entities": []
}
```

**After (real research):**
```json
{
  "facts": [
    {
      "claim": "Story about: TechCorp Layoffs",
      "verified": true,
      "source_count": 4
    },
    {
      "claim": "Involves: John Smith, Jane Doe",
      "verified": true,
      "entity_type": "PERSON"
    },
    {
      "claim": "Organizations: TechCorp, SEC",
      "verified": true,
      "entity_type": "ORG"
    }
  ],
  "sources": [
    {"url": "...", "type": "original"},
    {"url": "...", "type": "corroboration"},
    {"url": "...", "type": "corroboration"}
  ],
  "entities": {
    "people": ["John Smith", "Jane Doe"],
    "organizations": ["TechCorp", "SEC"],
    "locations": ["San Francisco"]
  },
  "verified": true,
  "source_count": 4
}
```

## Testing

```bash
# Run research tests
pytest tests/test_research.py -v

# Test with actual story (requires API keys)
python main.py
```

Watch logs for:
- `Entities extracted` - shows entity counts
- `Search completed` - shows search results
- `Research completed` - shows verification status
