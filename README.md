# GitHub Project - Django Application for GitHub Webhook Processing

## Overview
This is a standalone Django project designed to handle GitHub webhook events and provide GitHub API integration features.

## Features
- **GitHub Webhook Handler**: Process pull request events from GitHub
- **PR Information API**: Retrieve PR diffs and check-run results
- **Approval Request Workflow**: Submit PR details to external workflow engines
- **HMAC Signature Verification**: Verify GitHub webhook signatures for security
- **Email Verification Registration**: Require a verified email code before creating a user account

## Project Structure
```
github_project/
├── manage.py                 # Django management script
├── requirements.txt          # Python dependencies
├── config/                   # Django configuration
│   ├── settings.py          # Django settings (environment-based)
│   ├── urls.py              # URL routing
│   ├── wsgi.py              # WSGI application
│   └── asgi.py              # ASGI application
└── auth_model/                   # GitHub webhook app
    ├── apps.py              # App configuration
    ├── views.py             # Django views for webhook endpoints
    ├── urls.py              # URL patterns
    └── repo_dealing.py      # GitHub API interactions
```

## Installation

1. Clone or setup the project:
```bash
cd /Users/sjian/PycharmProjects/sweet-tea-backend/
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with required environment variables:
```bash
cp .env.example .env
```

5. Edit `.env` and set the following:
```
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=false
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com
POSTGRES_DB=sweettea
POSTGRES_HOST=your-postgres-host
POSTGRES_USER=netadmin
POSTGRES_PASSWORD=your-postgres-password
POSTGRES_PORT=5432
MAILERSEND_API_TOKEN=your-mailersend-token
MAILERSEND_FROM_EMAIL=verified-sender@example.com
MAILERSEND_FROM_NAME=Sweet Tea
GITHUB_WEBHOOK_SECRET=your-github-webhook-secret
GITHUB_TOKEN=ghp_your-github-token
APPROVAL_REQUEST_URL=http://your-approval-backend/api/ApprovalRequests
APPROVAL_REQUEST_AUTH=Bearer your-token-or-basic-auth
```

## Running the Application

### Development Server
```bash
python manage.py runserver 0.0.0.0:8000
```

### Production with Gunicorn
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

## API Endpoints

### Email Verification Registration

Registration requires verifying the email address first.

#### Request verification code
- **URL**: `POST /api/auth/request-code/`
- **Body**:
```json
{
  "email": "user@example.com",
  "name": "Optional Name"
}
```

#### Verify code
- **URL**: `POST /api/auth/verify-code/`
- **Body**:
```json
{
  "email": "user@example.com",
  "code": "123456"
}
```

#### Register account
- **URL**: `POST /api/auth/register/`
- **Body**:
```json
{
  "email": "user@example.com",
  "username": "user1",
  "password": "safe-password-123",
  "confirm_password": "safe-password-123",
  "first_name": "Optional",
  "last_name": "User",
  "display_name": "Neighborhood Helper",
  "location": "San Jose, CA",
  "profile_focus": "I am looking for community resources",
  "receive_updates": true,
  "nickname": "Jamie",
  "age_group": "adult",
  "language": "Japanese",
  "avatar_color": "Lavender",
  "self_introduction": "I like helping my community."
}
```

If the email has not been verified, registration returns `403` and no account is created. `username` is optional; if omitted, the backend uses `display_name`, `nickname`, or the email prefix.

#### Update account/profile
- **URL**: `POST /api/auth/account/update/`
- **Description**: Updates account and profile fields. Requires the existing account email and `current_password`.
- **Body**:
```json
{
  "email": "user@example.com",
  "current_password": "safe-password-123",
  "username": "updateduser",
  "first_name": "Jamie",
  "last_name": "Lee",
  "display_name": "Neighborhood Helper",
  "location": "San Jose, CA",
  "profile_focus": "I am looking for community resources",
  "receive_updates": true,
  "nickname": "Helper",
  "age_group": "adult",
  "language": "Japanese",
  "avatar_color": "Mint",
  "self_introduction": "Updated intro",
  "new_password": "new-safe-password-123",
  "confirm_new_password": "new-safe-password-123"
}
```

Email changes are intentionally rejected by this endpoint because a new email address should be verified first.

### GitHub Webhook
- **URL**: `POST /api/webhook/`
- **Description**: Receives GitHub webhook events
- **Headers**: 
  - `X-GitHub-Event`: Event type (e.g., 'pull_request')
  - `X-Hub-Signature-256`: HMAC-SHA256 signature for verification

**Supported Pull Request Actions**:
- `opened` - PR was opened
- `closed` - PR was closed (check merged flag)
- `synchronize` - New commits pushed to PR
- `reopened` - PR was reopened
- `review_requested` - Reviewer was requested
- And more...

### PR Information
- **URL**: `GET /api/pr-info/?repo=owner/repo&pr=123&sha=optional-sha`
- **Description**: Fetches PR diff and check-run results
- **Parameters**:
  - `repo` (required): Repository in format `owner/repo`
  - `pr` (required): Pull request number
  - `sha` (optional): Commit SHA (fetched from API if not provided)

**Response**:
```json
{
  "repo": "owner/repo",
  "pr": 123,
  "diff": "PR diff content...",
  "check_runs": [
    {
      "name": "Check name",
      "status": "completed",
      "conclusion": "success",
      "url": "https://..."
    }
  ]
}
```

## Configuration

All settings are loaded from environment variables. Edit your `.env` file to customize:

- `DJANGO_SECRET_KEY`: Django secret key (must be set in production)
- `DEBUG`: Set to 'true' for development, 'false' for production
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts
- `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`: PostgreSQL connection settings. Legacy `MYSQL_*` names are still accepted as fallbacks.
- `MAILERSEND_API_TOKEN`: MailerSend API token
- `MAILERSEND_FROM_EMAIL`: Verified MailerSend sender address
- `MAILERSEND_FROM_NAME`: Sender display name
- `EMAIL_VERIFICATION_CODE_TTL_MINUTES`: Verification code lifetime, defaults to `10`
- `EMAIL_VERIFICATION_MAX_ATTEMPTS`: Maximum failed code attempts, defaults to `5`
- `GITHUB_WEBHOOK_SECRET`: Secret configured in GitHub webhook settings
- `GITHUB_TOKEN`: GitHub personal access token with repo access
- `APPROVAL_REQUEST_URL`: URL of approval workflow backend
- `APPROVAL_REQUEST_AUTH`: Authorization header for approval requests
- `LOG_LEVEL`: Logging level (INFO, DEBUG, WARNING, ERROR)

## GitHub Token Permissions

Your `GITHUB_TOKEN` should have the following scopes:
- **Classic PAT**: `repo` scope for check runs and PR access
- **Fine-grained PAT**: 
  - Checks: Read
  - Pull requests: Read
  - Repository access to required repositories

## Security

- **Webhook Signature Verification**: Always verify GitHub signatures in production
- **HTTPS**: Use HTTPS for webhook URLs in production
- **Token Management**: Keep GitHub tokens in environment variables, never commit them
- **CSRF Protection**: Disabled for webhook endpoint (csrf_exempt) as GitHub doesn't provide CSRF tokens

## Troubleshooting

### SSO Block (403 Error)
If you see "403/SSO block" messages:
1. Visit GitHub Settings → Developer settings → Personal access tokens
2. Find your token and click "Configure SSO"
3. Authorize the token for your organization

### Webhook Not Triggering
1. Verify `GITHUB_WEBHOOK_SECRET` matches GitHub webhook settings
2. Check server logs for signature verification errors
3. Ensure webhook payload delivery is enabled in GitHub repository settings

### Check Runs Not Fetching
1. Verify `GITHUB_TOKEN` has required permissions
2. Check that the token is authorized for organization SAML/SSO
3. Verify repository access with the token

## License
[Your License Here]

## Support
For issues or questions, contact your development team.
