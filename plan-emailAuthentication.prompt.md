## Plan: Email Verification Authentication

Draft plan: add a Django authentication flow where users request an email verification code, receive it using the existing MailerSend function, verify the code, then create an account. This should also fix the current app/database configuration so Django can use PostgreSQL and persist users plus verification codes safely.

### Steps
1. Fix app registration in [`auth_model/apps.py`](/Users/sjian/PycharmProjects/sweet-tea-backend/auth_model/apps.py) and [`config/settings.py`](/Users/sjian/PycharmProjects/sweet-tea-backend/config/settings.py) to use `auth_model`.
2. Configure PostgreSQL in [`config/settings.py`](/Users/sjian/PycharmProjects/sweet-tea-backend/config/settings.py) using environment variables, not hardcoded DB credentials.
3. Add authentication models in [`auth_model/models.py`](/Users/sjian/PycharmProjects/sweet-tea-backend/auth_model/models.py), especially `EmailVerificationCode`.
4. Refactor `send_email` in [`auth_model/auth_data.py`](/Users/sjian/PycharmProjects/sweet-tea-backend/auth_model/auth_data.py) to send dynamic verification codes.
5. Add API views in [`auth_model/views.py`](/Users/sjian/PycharmProjects/sweet-tea-backend/auth_model/views.py) for request-code, verify-code, and register.
6. Add auth routes in [`auth_model/urls.py`](/Users/sjian/PycharmProjects/sweet-tea-backend/auth_model/urls.py) under the existing `/github/api/` prefix.

### Further Considerations
1. Use Django’s built-in `User` model unless you need custom user fields now.
2. Move MailerSend token/from-address and DB password into `.env`; current hardcoded email token should be rotated.
3. Your DB config says `MYSQL_*` but uses `psycopg2`; recommend renaming to `POSTGRES_*`.

