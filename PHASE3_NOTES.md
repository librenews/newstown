# Phase 3 Implementation Notes

## Email Provider Setup

### SendGrid Configuration

**Default provider**: SendGrid (modular design allows switching)

#### Setup Steps

1. **Get SendGrid API Key**
   ```bash
   # Sign up at https://sendgrid.com
   # Navigate to Settings > API Keys
   # Create new API key with "Mail Send" permissions
   ```

2. **Add to Environment**
   ```bash
   # .env
   SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxx
   EMAIL_FROM_ADDRESS=news@yourdomain.com
   EMAIL_FROM_NAME=Your News Town
   ```

3. **Verify Domain** (optional but recommended)
   - Add DNS records for sender authentication
   - Improves deliverability

#### Alternative Providers

The email system uses a **provider interface** pattern. To switch providers:

**AWS SES**:
```python
class SESProvider(EmailProvider):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str):
        self.client = boto3.client('ses', region_name=region, ...)
```

**Mailgun**:
```python
class MailgunProvider(EmailProvider):
    def __init__(self, api_key: str, domain: str):
        self.api_key = api_key
        self.domain = domain
```

**SMTP (any provider)**:
```python
class SMTPProvider(EmailProvider):
    def __init__(self, host: str, port: int, username: str, password: str):
        # Standard SMTP implementation
```

Simply implement the `EmailProvider` interface and update the factory function in `publishing/email.py`.

---

## Dependencies to Add

```bash
# requirements.txt additions for Phase 3
sendgrid==6.11.0  # Email publishing
feedgen==1.0.0    # RSS feed generation
tweepy==4.14.0    # Twitter API (optional)
atproto==0.0.46   # Bluesky API (optional)
```

---

## Environment Variables Summary

**Required for Phase 3**:
- `SENDGRID_API_KEY` - Email newsletter delivery
- `EMAIL_FROM_ADDRESS` - Sender email address
- `EMAIL_FROM_NAME` - Sender display name

**Optional**:
- `TWITTER_API_KEY` - Twitter publishing
- `TWITTER_API_SECRET`
- `BLUESKY_HANDLE` - Bluesky publishing  
- `BLUESKY_APP_PASSWORD`

---

## Testing Email Locally

**Option 1**: SendGrid Test Mode
```python
# Use SendGrid sandbox mode
# Emails won't actually send, but API validates them
```

**Option 2**: Mailtrap
```python
# Use Mailtrap.io for dev/testing
# Catches all emails in inbox, doesn't deliver
```

**Option 3**: Print to Console
```python
# For local dev, can implement ConsoleEmailProvider
class ConsoleEmailProvider(EmailProvider):
    async def send_email(self, ...):
        print(f"EMAIL: {subject}\n{text}")
        return True
```

---

## Migration Path

**Current state**: No email capability  
**Phase 3**: Add SendGrid module  
**Future**: Can swap providers without changing application logic

The abstraction layer ensures vendor lock-in is avoided.
