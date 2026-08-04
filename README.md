# GitHub Project - Django Application for GitHub Webhook Processing

## Overview
This is a standalone Django project designed to handle GitHub webhook events and provide GitHub API integration features.

## Features
- **GitHub Webhook Handler**: Process pull request events from GitHub
- **PR Information API**: Retrieve PR diffs and check-run results
- **Approval Request Workflow**: Submit PR details to external workflow engines
- **HMAC Signature Verification**: Verify GitHub webhook signatures for security

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

### GitHub Webhook
- **URL**: `POST /github/api/webhook/`
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
- **URL**: `GET /github/api/pr-info/?repo=owner/repo&pr=123&sha=optional-sha`
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
