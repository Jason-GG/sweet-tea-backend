import time
import requests
import logging
from django.conf import settings

"""Module for handling GitHub repository interactions, such as processing pull request events.
This module can be expanded with functions to interact with the GitHub API, manage repository data,and implement business logic related to repository management.
"""
logger = logging.getLogger(__name__)
access_token = "mlsn.30c9e8972e8e24b4d035fd6d98ca79332094d36a01b9ed64114c6d22605c0f01"
mail_url = "https://api.mailersend.com/v1/email"

def send_email():
    payload = {
        "from": {
            "email": "MS_peZn6j@test-2p0347zee5klzdrn.mlsender.net",
            "name": "MailerSend"
        },
        "to": [
            {
                "email": "jianshun1120@hotmail.com",
                "name": "John Mailer"
            }
        ],
        "subject": "Hello from {{company}}!",
        "text": "This is just a friendly hello from your friends at {{company}}.",
        "html": "<b>This is just a friendly hello from your friends at {{company}}.</b>",
        "personalization": [
            {
                "email": "jianshun1120@hotmail.com",
                "data": {
                    "company": "MailerSend"
                }
            }
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    result = requests.post(mail_url, json=payload, headers=headers)
    print(result.text)



if __name__ == "__main__":
    send_email()