import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
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
        """Initialize the Gmail API service for mocdatapty@gmail.com account"""
        try:
            # Load OAuth2 credentials from file
            credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
            
            if not os.path.exists(credentials_path):
                logger.error("OAuth2 credentials.json file not found!")
                logger.error("Please create credentials.json file with OAuth2 credentials for mocdatapty@gmail.com account")
                self.service = None
                return
            
            # Use OAuth2 credentials for mocdatapty@gmail.com
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            import pickle
            
            # Gmail API scopes
            SCOPES = [
                'https://www.googleapis.com/auth/gmail.send',
                'https://www.googleapis.com/auth/gmail.readonly'
            ]
            
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
            
            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail service initialized with OAuth2 credentials for mocdatapty@gmail.com account")
            
        except Exception as e:
            logger.error(f"Error initializing Gmail service: {str(e)}")
            self.service = None
    
    def send_email(self, to_email, subject, body, from_email=None, attachments=None):
        """
        Send email using Google Cloud API with OAuth2 (NO SMTP FALLBACK)
        
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
                    'error': 'OAuth2 Gmail service not initialized. Please set up proper OAuth2 credentials for mocdatapty@gmail.com account.'
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
                try:
                    user_info = self.service.users().getProfile(userId='me').execute()
                    oauth2_email = user_info.get('emailAddress', 'noreply@eclick.com')
                    message['from'] = oauth2_email
                    logger.info(f"Using OAuth2 account email: {oauth2_email}")
                except HttpError as e:
                    if e.resp.status == 403:
                        logger.error("Insufficient OAuth2 scopes. Need 'gmail.readonly' scope to read user profile.")
                        logger.error("Please re-authenticate with updated scopes.")
                    else:
                        logger.error(f"Gmail API error getting user profile: {e}")
                    message['from'] = 'noreply@eclick.com'  # Fallback
                except Exception as e:
                    logger.warning(f"Could not get OAuth2 user email: {e}")
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
            sent_message = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            return {
                'success': True,
                'message_id': sent_message['id'],
                'message': 'Email sent successfully'
            }
            
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            return {
                'success': False,
                'error': f'Gmail API error: {str(error)}'
            }
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
        """Create HTML formatted report"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>E-Click Project Management Report</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #000000;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f8f9fa;
                }}
                .container {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    border-bottom: 3px solid #dc2626;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }}
                .header h1 {{
                    color: #dc2626;
                    margin: 0;
                    font-size: 28px;
                }}
                .header p {{
                    color: #6b7280;
                    margin: 10px 0 0 0;
                }}
                .donut-chart {{
                    text-align: center;
                    margin: 30px 0;
                }}
                .donut-container {{
                    position: relative;
                    display: inline-block;
                    width: 150px;
                    height: 150px;
                }}
                .donut-svg {{
                    width: 150px;
                    height: 150px;
                    transform: rotate(-90deg);
                }}
                .donut-circle {{
                    fill: none;
                    stroke-width: 12;
                }}
                .donut-progress {{
                    stroke: #dc2626;
                    stroke-linecap: round;
                    transition: stroke-dasharray 0.3s ease;
                }}
                .donut-remaining {{
                    stroke: #000000;
                    stroke-linecap: round;
                }}
                .donut-center {{
                    position: absolute;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    text-align: center;
                }}
                .donut-percentage {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #000000;
                    margin: 0;
                }}
                .donut-label {{
                    font-size: 12px;
                    color: #6b7280;
                    margin: 0;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .stat-card {{
                    background: #ffffff;
                    border: 2px solid #dc2626;
                    color: #000000;
                    padding: 20px;
                    border-radius: 8px;
                    text-align: center;
                }}
                .stat-card h3 {{
                    margin: 0 0 10px 0;
                    font-size: 24px;
                    color: #dc2626;
                }}
                .stat-card p {{
                    margin: 0;
                    color: #000000;
                }}
                .section {{
                    margin-bottom: 30px;
                }}
                .section h2 {{
                    color: #dc2626;
                    border-bottom: 2px solid #dc2626;
                    padding-bottom: 10px;
                    margin-bottom: 20px;
                }}
                .insight {{
                    background-color: #ffffff;
                    border: 1px solid #000000;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 10px 0;
                    border-left: 4px solid #dc2626;
                }}
                .recommendation {{
                    background-color: #ffffff;
                    border: 1px solid #000000;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 10px 0;
                    border-left: 4px solid #dc2626;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 1px solid #dc2626;
                    color: #dc2626;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 E-Click Project Management Report</h1>
                    <p>Generated on {report_data.get('generated_date', 'Recent')}</p>
                </div>
                
                {f'<div class="insight"><strong>💬 Custom Message:</strong><br>{custom_message}</div>' if custom_message else ''}
                
                <!-- DONUT CHART -->
                <div class="donut-chart">
                    <div class="donut-container">
                        <svg class="donut-svg">
                            <circle class="donut-circle donut-remaining" cx="75" cy="75" r="60" stroke-dasharray="377 377"></circle>
                            <circle class="donut-circle donut-progress" cx="75" cy="75" r="60" stroke-dasharray="{377 * report_data.get('task_completion_rate', 0) / 100} 377"></circle>
                        </svg>
                        <div class="donut-center">
                            <div class="donut-percentage">{report_data.get('task_completion_rate', 0):.1f}%</div>
                            <div class="donut-label">Completed</div>
                        </div>
                    </div>
                    <div style="margin-top: 15px;">
                        <span style="color: #000000; font-size: 14px;">
                            <span style="display: inline-block; width: 12px; height: 12px; background: #dc2626; border-radius: 50%; margin-right: 8px;"></span>
                            Completed: {report_data.get('task_completion_rate', 0):.1f}%
                        </span>
                        <span style="margin-left: 20px; color: #000000; font-size: 14px;">
                            <span style="display: inline-block; width: 12px; height: 12px; background: #000000; border-radius: 50%; margin-right: 8px;"></span>
                            Remaining: {100 - report_data.get('task_completion_rate', 0):.1f}%
                        </span>
                    </div>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>{report_data.get('total_projects', 0)}</h3>
                        <p>Total Projects</p>
                    </div>
                    <div class="stat-card">
                        <h3>{report_data.get('projects_completed', 0)}</h3>
                        <p>Completed Projects</p>
                    </div>
                    <div class="stat-card">
                        <h3>{report_data.get('total_tasks', 0)}</h3>
                        <p>Total Tasks</p>
                    </div>
                    <div class="stat-card">
                        <h3>{report_data.get('completed_tasks', 0)}</h3>
                        <p>Completed Tasks</p>
                    </div>
                </div>
                
                <div class="section">
                    <h2>📈 Performance Metrics</h2>
                    
                    <div class="insight">
                        <strong>Project Completion Rate:</strong>
                        <div style="background-color: #e5e7eb; border-radius: 10px; height: 20px; margin: 10px 0; overflow: hidden;">
                            <div style="height: 100%; background: #dc2626; border-radius: 10px; width: {report_data.get('project_completion_rate', 0)}%;"></div>
                        </div>
                        <p>{report_data.get('project_completion_rate', 0):.1f}%</p>
                    </div>
                    
                    <div class="insight">
                        <strong>Task Completion Rate:</strong>
                        <div style="background-color: #e5e7eb; border-radius: 10px; height: 20px; margin: 10px 0; overflow: hidden;">
                            <div style="height: 100%; background: #dc2626; border-radius: 10px; width: {report_data.get('task_completion_rate', 0)}%;"></div>
                        </div>
                        <p>{report_data.get('task_completion_rate', 0):.1f}%</p>
                    </div>
                    
                    <div class="insight">
                        <strong>User Engagement Rate:</strong>
                        <div style="background-color: #e5e7eb; border-radius: 10px; height: 20px; margin: 10px 0; overflow: hidden;">
                            <div style="height: 100%; background: #dc2626; border-radius: 10px; width: {report_data.get('user_engagement_rate', 0)}%;"></div>
                        </div>
                        <p>{report_data.get('user_engagement_rate', 0):.1f}%</p>
                    </div>
                </div>
                
                <div class="section">
                    <h2>🎯 Key Insights</h2>
                    {self._generate_insights_html(report_data)}
                </div>
                
                <div class="section">
                    <h2>💡 Recommendations</h2>
                    {self._generate_recommendations_html(report_data)}
                </div>
                
                <div class="footer">
                    <p>This report was generated automatically by the E-Click Project Management System.</p>
                    <p>For questions or support, please contact your system administrator.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def _generate_insights_html(self, report_data):
        """Generate insights HTML based on report data"""
        insights = []
        
        project_completion_rate = report_data.get('project_completion_rate', 0)
        task_completion_rate = report_data.get('task_completion_rate', 0)
        user_engagement_rate = report_data.get('user_engagement_rate', 0)
        
        if project_completion_rate >= 80:
            insights.append("🏆 <strong>Excellent Project Performance:</strong> Your project completion rate is outstanding!")
        elif project_completion_rate >= 60:
            insights.append("✅ <strong>Good Project Performance:</strong> Your projects are progressing well.")
        else:
            insights.append("⚠️ <strong>Project Performance Needs Attention:</strong> Consider focusing on project completion.")
        
        if task_completion_rate >= 75:
            insights.append("⚡ <strong>High Task Efficiency:</strong> Your team is completing tasks efficiently.")
        elif task_completion_rate >= 50:
            insights.append("📊 <strong>Moderate Task Efficiency:</strong> Task completion is progressing steadily.")
        else:
            insights.append("⏳ <strong>Task Efficiency Needs Improvement:</strong> Consider task prioritization strategies.")
        
        if user_engagement_rate >= 85:
            insights.append("👥 <strong>Strong Team Engagement:</strong> Your team is highly active and engaged.")
        elif user_engagement_rate >= 60:
            insights.append("👍 <strong>Good Team Engagement:</strong> Team participation is at a healthy level.")
        else:
            insights.append("📉 <strong>Low Team Engagement:</strong> Consider strategies to increase user participation.")
        
        insights_html = ""
        for insight in insights:
            insights_html += f'<div class="insight">{insight}</div>'
        
        return insights_html
    
    def _generate_recommendations_html(self, report_data):
        """Generate recommendations HTML based on report data"""
        recommendations = []
        
        project_completion_rate = report_data.get('project_completion_rate', 0)
        task_completion_rate = report_data.get('task_completion_rate', 0)
        user_engagement_rate = report_data.get('user_engagement_rate', 0)
        
        if project_completion_rate < 60:
            recommendations.append("🚀 <strong>Accelerate Project Delivery:</strong> Focus on completing projects in progress to improve overall completion rate.")
        
        if task_completion_rate < 50:
            recommendations.append("⚡ <strong>Implement Task Prioritization:</strong> Develop a framework to prioritize and track task completion.")
        
        if user_engagement_rate < 70:
            recommendations.append("👥 <strong>Enhance User Engagement:</strong> Develop strategies to increase team participation and system usage.")
        
        if project_completion_rate >= 80 and task_completion_rate >= 75:
            recommendations.append("🏆 <strong>Maintain Excellence:</strong> Your current performance is excellent. Continue with current practices.")
        
        if not recommendations:
            recommendations.append("📈 <strong>Continuous Monitoring:</strong> Track key metrics regularly to identify improvement opportunities.")
        
        recommendations_html = ""
        for rec in recommendations:
            recommendations_html += f'<div class="recommendation">{rec}</div>'
        
        return recommendations_html

# Create a global instance
email_service = GoogleCloudEmailService() 