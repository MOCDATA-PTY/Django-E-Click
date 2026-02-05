import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
# from google.oauth2 import service_account
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class GoogleCloudEmailService:
    def __init__(self):
        self.api_key = 'AIzaSyBAHeuA83Rl--GvorBIZlY8UOratOu-X2U'
        self.service_account_email = None
        self.credentials = None
        self.service = None
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize the Gmail API service"""
        try:
            # Try to load OAuth2 credentials from file
            credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
            
            if os.path.exists(credentials_path):
                # Use OAuth2 credentials
                # from google_auth_oauthlib.flow import InstalledAppFlow
                # from google.auth.transport.requests import Request
                # from googleapiclient.discovery import build
                import pickle
                
                # Gmail API scopes
                SCOPES = ['https://www.googleapis.com/auth/gmail.send']
                
                # Check if we have a token file
                token_path = os.path.join(os.path.dirname(__file__), 'token.pickle')
                
                creds = None
                if os.path.exists(token_path):
                    with open(token_path, 'rb') as token:
                        creds = pickle.load(token)
                
                # If there are no (valid) credentials available, let the user log in
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    else:
                        flow = InstalledAppFlow.from_client_secrets_file(
                            credentials_path, SCOPES)
                        creds = flow.run_local_server(port=55691, prompt='consent')
                    
                    # Save the credentials for the next run
                    with open(token_path, 'wb') as token:
                        pickle.dump(creds, token)
                
                # self.service = build('gmail', 'v1', credentials=creds)
                # logger.info("Gmail service initialized with OAuth2 credentials")
                
            else:
                # Fallback to API key (limited functionality)
                # from googleapiclient.discovery import build
                
                # Note: Gmail API requires OAuth2 for full functionality
                # API key can be used for other Google Cloud services
                self.service = None
                logger.warning("No OAuth2 credentials found. Gmail API requires OAuth2 authentication.")
                logger.info("Please create a credentials.json file with your OAuth2 credentials.")
            
        except Exception as e:
            logger.error(f"Error initializing Gmail service: {str(e)}")
            self.service = None
    
    def send_email(self, to_email, subject, body, from_email=None, attachments=None):
        """
        Send email using Google Cloud API
        
        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            body (str): Email body (HTML or plain text)
            from_email (str): Sender email (optional, uses default if not provided)
            attachments (list): List of attachment file paths (optional)
        
        Returns:
            dict: Response with success status and message
        """
        try:
            if not self.service:
                return {
                    'success': False,
                    'error': 'Gmail service not initialized. Please set up proper OAuth2 credentials.'
                }
            
            # Create message
            message = MIMEMultipart()
            message['to'] = to_email
            message['subject'] = subject
            
            # Set sender - use OAuth2 account email or provided email
            if from_email:
                message['from'] = from_email
            else:
                # Get the email from OAuth2 credentials
                # try:
                #     user_info = self.service.users().getProfile(userId='me').execute()
                #     oauth2_email = user_info.get('emailAddress', 'noreply@eclick.com')
                #     message['from'] = oauth2_email
                # except Exception as e:
                #     logger.warning(f"Could not get OAuth2 user email: {e}")
                message['from'] = 'noreply@eclick.com'  # Fallback
            
            # Add body
            if '<html>' in body.lower():
                # HTML content
                text_part = MIMEText(body, 'html')
            else:
                # Plain text content
                text_part = MIMEText(body, 'plain')
            
            message.attach(text_part)
            
            # Add attachments if provided
            if attachments:
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        with open(attachment_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                        
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename= {os.path.basename(attachment_path)}'
                        )
                        message.attach(part)
            
            # Encode the message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send the email
            # sent_message = self.service.users().messages().send(
            #     userId='me',
            #     body={'raw': raw_message}
            # ).execute()
            
            return {
                'success': False,
                'error': 'Gmail service disabled - no email sent'
            }
            
        # except HttpError as error:
        #     logger.error(f"Gmail API error: {error}")
        #     return {
        #         'success': False,
        #         'error': f'Gmail API error: {str(error)}'
        #     }
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending email: {str(e)}'
            }
    
    def send_report_email(self, to_email, report_data, custom_message=''):
        """
        Send a formatted report email
        
        Args:
            to_email (str): Recipient email address
            report_data (dict): Report data containing statistics
            custom_message (str): Custom message to include
        
        Returns:
            dict: Response with success status and message
        """
        try:
            # Create HTML email body
            html_body = self._create_report_html(report_data, custom_message)
            
            subject = f"E-Click Project Management Report - {report_data.get('date_range', 'Recent Period')}"
            
            return self.send_email(
                to_email=to_email,
                subject=subject,
                body=html_body,
                from_email=None,  # Will use OAuth2 account email
            )
            
        except Exception as e:
            logger.error(f"Error sending report email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending report email: {str(e)}'
            }
    
    def _create_report_html(self, report_data, custom_message):
        """Create HTML formatted report - Simple and professional"""
        html = f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p><strong>E-Click Project Management Report</strong></p>
    <p>Generated on {report_data.get('generated_date', 'Recent')}</p>

    {f'<p><strong>Custom Message:</strong><br>{custom_message}</p>' if custom_message else ''}

    <p><strong>Summary Statistics:</strong></p>
    <p>Total Projects: {report_data.get('total_projects', 0)}</p>
    <p>Completed Projects: {report_data.get('projects_completed', 0)}</p>
    <p>Total Tasks: {report_data.get('total_tasks', 0)}</p>
    <p>Completed Tasks: {report_data.get('completed_tasks', 0)}</p>
    <p>Task Completion Rate: {report_data.get('task_completion_rate', 0):.1f}%</p>

    <p><strong>Performance Metrics:</strong></p>
    <p>Project Completion Rate: {report_data.get('project_completion_rate', 0):.1f}%</p>
    <p>Task Completion Rate: {report_data.get('task_completion_rate', 0):.1f}%</p>
    <p>User Engagement Rate: {report_data.get('user_engagement_rate', 0):.1f}%</p>

    <p><strong>Key Insights:</strong></p>
    {self._generate_insights_html(report_data)}

    <p><strong>Recommendations:</strong></p>
    {self._generate_recommendations_html(report_data)}

    <hr>
    <p>This report was generated automatically by the E-Click Project Management System.</p>
    <p>For questions or support, please contact your system administrator.</p>
</body>
</html>"""
        return html
    
    def _generate_insights_html(self, report_data):
        """Generate insights HTML based on report data - Simple and professional"""
        insights = []

        project_completion_rate = report_data.get('project_completion_rate', 0)
        task_completion_rate = report_data.get('task_completion_rate', 0)
        user_engagement_rate = report_data.get('user_engagement_rate', 0)

        if project_completion_rate >= 80:
            insights.append("<strong>Excellent Project Performance:</strong> Your project completion rate is outstanding!")
        elif project_completion_rate >= 60:
            insights.append("<strong>Good Project Performance:</strong> Your projects are progressing well.")
        else:
            insights.append("<strong>Project Performance Needs Attention:</strong> Consider focusing on project completion.")

        if task_completion_rate >= 75:
            insights.append("<strong>High Task Efficiency:</strong> Your team is completing tasks efficiently.")
        elif task_completion_rate >= 50:
            insights.append("<strong>Moderate Task Efficiency:</strong> Task completion is progressing steadily.")
        else:
            insights.append("<strong>Task Efficiency Needs Improvement:</strong> Consider task prioritization strategies.")

        if user_engagement_rate >= 85:
            insights.append("<strong>Strong Team Engagement:</strong> Your team is highly active and engaged.")
        elif user_engagement_rate >= 60:
            insights.append("<strong>Good Team Engagement:</strong> Team participation is at a healthy level.")
        else:
            insights.append("<strong>Low Team Engagement:</strong> Consider strategies to increase user participation.")

        insights_html = ""
        for insight in insights:
            insights_html += f'<p>{insight}</p>'

        return insights_html
    
    def _generate_recommendations_html(self, report_data):
        """Generate recommendations HTML based on report data - Simple and professional"""
        recommendations = []

        project_completion_rate = report_data.get('project_completion_rate', 0)
        task_completion_rate = report_data.get('task_completion_rate', 0)
        user_engagement_rate = report_data.get('user_engagement_rate', 0)

        if project_completion_rate < 60:
            recommendations.append("<strong>Accelerate Project Delivery:</strong> Focus on completing projects in progress to improve overall completion rate.")

        if task_completion_rate < 50:
            recommendations.append("<strong>Implement Task Prioritization:</strong> Develop a framework to prioritize and track task completion.")

        if user_engagement_rate < 70:
            recommendations.append("<strong>Enhance User Engagement:</strong> Develop strategies to increase team participation and system usage.")

        if project_completion_rate >= 80 and task_completion_rate >= 75:
            recommendations.append("<strong>Maintain Excellence:</strong> Your current performance is excellent. Continue with current practices.")

        if not recommendations:
            recommendations.append("<strong>Continuous Monitoring:</strong> Track key metrics regularly to identify improvement opportunities.")

        recommendations_html = ""
        for rec in recommendations:
            recommendations_html += f'<p>{rec}</p>'

        return recommendations_html

# Create a global instance - DISABLED
# email_service = GoogleCloudEmailService() 