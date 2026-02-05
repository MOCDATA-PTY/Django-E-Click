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
                # Check if there's an HTML alternative
                html_body = None
                if hasattr(message, 'alternatives') and message.alternatives:
                    for content, mimetype in message.alternatives:
                        if mimetype == 'text/html':
                            html_body = content
                            break

                # Determine content type - check alternatives first, then content_subtype
                if html_body:
                    body_content = html_body
                    body_type = "HTML"
                    logger.info(f"[GRAPH API] Using HTML body from alternatives ({len(html_body)} chars)")
                elif hasattr(message, 'content_subtype') and message.content_subtype == 'html':
                    body_content = message.body
                    body_type = "HTML"
                    logger.info(f"[GRAPH API] Using HTML body from content_subtype")
                else:
                    body_content = message.body
                    body_type = "Text"
                    logger.info(f"[GRAPH API] Using plain text body")

                graph_message = {
                    "message": {
                        "subject": message.subject,
                        "body": {
                            "contentType": body_type,
                            "content": body_content
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

                # Add attachments if present
                if hasattr(message, 'attachments') and message.attachments:
                    import base64
                    graph_message["message"]["attachments"] = []
                    logger.info(f"[GRAPH API] Processing {len(message.attachments)} attachments")

                    for idx, attachment in enumerate(message.attachments):
                        logger.info(f"[GRAPH API] Attachment {idx}: type={type(attachment)}")

                        if hasattr(attachment, 'get_payload'):
                            # MIMEImage or similar MIME object
                            content = attachment.get_payload(decode=True)
                            filename = attachment.get_filename() or f"attachment{idx}"
                            content_type = attachment.get_content_type()
                            content_id = attachment.get('Content-ID', '').strip('<>')

                            logger.info(f"[GRAPH API]   filename={filename}, content_type={content_type}, content_id={content_id}")

                            att_data = {
                                "@odata.type": "#microsoft.graph.fileAttachment",
                                "name": filename,
                                "contentType": content_type,
                                "contentBytes": base64.b64encode(content).decode(),
                                "isInline": bool(content_id)
                            }
                            if content_id:
                                att_data["contentId"] = content_id

                            graph_message["message"]["attachments"].append(att_data)
                            logger.info(f"[GRAPH API]   Added attachment successfully")

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
