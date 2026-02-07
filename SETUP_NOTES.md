# Additional Setup Steps

After installing dependencies, you'll need to download the spaCy language model:

```bash
source venv/bin/activate  # or venv\Scripts\activate on Windows
python -m spacy download en_core_web_sm
```

This downloads the English language model needed for entity extraction.

## Brave Search API

To enable web search for research:

1. Get a Brave Search API key from: https://brave.com/search/api/
2. Add it to your `.env` file:
   ```
   BRAVE_API_KEY=BSA...
   ```

Without this key, research will still work but won't search for corroborating sources.
