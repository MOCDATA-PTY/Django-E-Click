"""
Microsoft Graph API Email Backend
Sends emails via Microsoft Graph API instead of SMTP
"""
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings
import msal
import requests
import logging

logger = logging.getLogger(__name__)

class GraphEmailBackend(BaseEmailBackend):
    """
    Email backend that uses Microsoft Graph API to send emails
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_id = settings.GRAPH_CLIENT_ID
        self.client_secret = settings.GRAPH_CLIENT_SECRET
        self.tenant_id = settings.GRAPH_TENANT_ID
        self.from_email = settings.DEFAULT_FROM_EMAIL

    def get_access_token(self):
        """Get access token using client credentials flow"""
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=authority,
            client_credential=self.client_secret,
        )

        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" in result:
            return result["access_token"]
        else:
            error = result.get("error_description", result.get("error"))
            raise Exception(f"Failed to acquire token: {error}")

    def send_messages(self, email_messages):
        """Send email messages using Microsoft Graph API"""
        if not email_messages:
            return 0

        try:
            access_token = self.get_access_token()
        except Exception as e:
            logger.error(f"[GRAPH API] Failed to get access token: {e}")
            if not self.fail_silently:
                raise
            return 0

        sent_count = 0

        for message in email_messages:
            try:
                # Prepare the email message for Graph API
                graph_message = {
                    "message": {
                        "subject": message.subject,
                        "body": {
                            "contentType": "Text" if message.content_subtype == "plain" else "HTML",
                            "content": message.body
                        },
                        "toRecipients": [
                            {"emailAddress": {"address": addr}} for addr in message.to
                        ],
                    }
                }

                # Add CC recipients if present
                if message.cc:
                    graph_message["message"]["ccRecipients"] = [
                        {"emailAddress": {"address": addr}} for addr in message.cc
                    ]

                # Add BCC recipients if present
                if message.bcc:
                    graph_message["message"]["bccRecipients"] = [
                        {"emailAddress": {"address": addr}} for addr in message.bcc
                    ]

                # Determine which email to send from
                from_address = message.from_email or self.from_email

                # Send email via Graph API
                endpoint = f"https://graph.microsoft.com/v1.0/users/{from_address}/sendMail"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }

                logger.info(f"[GRAPH API] Sending email to: {', '.join(message.to)}")

                response = requests.post(endpoint, json=graph_message, headers=headers)

                if response.status_code == 202:
                    logger.info(f"[GRAPH API] Successfully sent email to {', '.join(message.to)}")
                    sent_count += 1
                else:
                    error_msg = f"Failed to send email: {response.status_code} - {response.text}"
                    logger.error(f"[GRAPH API] {error_msg}")
                    if not self.fail_silently:
                        raise Exception(error_msg)

            except Exception as e:
                logger.error(f"[GRAPH API] Error sending email: {e}")
                if not self.fail_silently:
                    raise

        return sent_count
