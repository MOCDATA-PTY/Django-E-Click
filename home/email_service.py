import os
import base64
import tempfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from django.http import HttpResponse
import logging

logger = logging.getLogger(__name__)

class SimpleEmailService:
    """Simple email service using Django's built-in email functionality"""
    
    def __init__(self):
        self.from_email = settings.DEFAULT_FROM_EMAIL
        self.logger = logging.getLogger(__name__)
    
    def send_otp_email(self, to_email, otp, client_username, project_name, site_url=None):
        """
        Send OTP email for client password setup
        
        Args:
            to_email (str): Client's email address
            otp (str): 6-digit OTP code
            client_username (str): Client's username
            project_name (str): Project name for context
            site_url (str): Base URL of the site for creating links
        
        Returns:
            dict: Response with success status and message
        """
        try:
            subject = f"Set Your Password - {project_name} Project"
            
            # Create simple text email
            text_body = self._create_simple_otp_text(otp, client_username, project_name, site_url)
            
            # Send email as plain text
            email = EmailMessage(
                subject=subject,
                body=text_body,
                from_email=self.from_email,
                to=[to_email]
            )
            
            email.send()
            
            self.logger.info(f"OTP email sent successfully to {to_email}")
            return {
                'success': True,
                'message': 'OTP email sent successfully'
            }
            
        except Exception as e:
            self.logger.error(f"Error sending OTP email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending OTP email: {str(e)}'
            }
    
    def send_user_otp_email(self, to_email, otp, username, site_url=None):
        """
        Send OTP email for user password setup
        
        Args:
            to_email (str): User's email address
            otp (str): 6-digit OTP code
            username (str): User's username
            site_url (str): Base URL of the site for creating links
        
        Returns:
            dict: Response with success status and message
        """
        try:
            subject = f"Set Your Password - Welcome to E-Click"
            
            # Create simple text email
            text_body = self._create_simple_user_otp_text(otp, username, site_url)
            
            # Send email as plain text
            email = EmailMessage(
                subject=subject,
                body=text_body,
                from_email=self.from_email,
                to=[to_email]
            )
            
            email.send()
            
            self.logger.info(f"User OTP email sent successfully to {to_email}")
            return {
                'success': True,
                'message': 'User OTP email sent successfully'
            }
            
        except Exception as e:
            self.logger.error(f"Error sending user OTP email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending user OTP email: {str(e)}'
            }
    
    def send_password_reset_otp_email(self, to_email, otp, username, site_url=None):
        """
        Send OTP email for user password reset
        
        Args:
            to_email (str): User's email address
            otp (str): 6-digit OTP code
            username (str): User's username
            site_url (str): Base URL of the site for creating links
        
        Returns:
            dict: Response with success status and message
        """
        try:
            subject = f"Password Reset OTP - E-Click"
            
            # Create simple text email
            text_body = self._create_simple_password_reset_otp_text(otp, username, site_url)
            
            # Send email as plain text
            email = EmailMessage(
                subject=subject,
                body=text_body,
                from_email=self.from_email,
                to=[to_email]
            )
            
            email.send()
            
            self.logger.info(f"Password reset OTP email sent successfully to {to_email}")
            return {
                'success': True,
                'message': 'Password reset OTP email sent successfully'
            }
            
        except Exception as e:
            self.logger.error(f"Error sending password reset OTP email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending password reset OTP email: {str(e)}'
            }
    
    def _create_otp_html(self, otp, client_username, project_name, site_url=None):
        """Create HTML formatted OTP email with Gantt chart styling"""
        # Create the setup password URL with username parameter (URL encoded)
        from urllib.parse import quote
        encoded_username = quote(client_username)
        setup_url = f"{site_url}/client/setup-password/?username={encoded_username}" if site_url else f"/client/setup-password/?username={encoded_username}"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Set Your Password - {project_name}</title>
            <style>
                :root {{
                    --primary-red: #DC2626;
                    --secondary-red: #EF4444;
                    --background-primary: #ffffff;
                    --background-secondary: #F9FAFB;
                    --background-gray: #F3F4F6;
                    --background-tertiary: #FEF2F2;
                    --text-primary: #111827;
                    --text-secondary: #6B7280;
                    --text-muted: #9CA3AF;
                    --border-light: #E5E7EB;
                    --shadow-light: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
                    --shadow-medium: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                }}
                
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: var(--text-primary);
                    background-color: var(--background-secondary);
                    padding: 20px;
                    font-size: 14px;
                }}
                
                .email-container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: var(--background-primary);
                    border-radius: 12px;
                    box-shadow: var(--shadow-medium);
                    overflow: hidden;
                    border: 1px solid var(--border-light);
                }}
                
                .email-header {{
                    background: linear-gradient(135deg, var(--primary-red), var(--secondary-red));
                    color: white;
                    padding: 2rem;
                    text-align: center;
                    border-bottom: 3px solid var(--primary-red);
                }}
                
                .email-header h1 {{
                    font-size: 1.5rem;
                    font-weight: 700;
                    margin-bottom: 0.5rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 0.75rem;
                }}
                
                .email-header .subtitle {{
                    font-size: 0.875rem;
                    opacity: 0.9;
                }}
                
                .email-content {{
                    padding: 2rem;
                }}
                
                .welcome-section {{
                    background: var(--background-primary);
                    border-radius: 12px;
                    padding: 1.5rem;
                    box-shadow: var(--shadow-light);
                    border: 1px solid var(--border-light);
                    margin-bottom: 1.5rem;
                    position: relative;
                    overflow: hidden;
                }}
                
                .welcome-section::before {{
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 4px;
                    height: 100%;
                    background: var(--primary-red);
                }}
                
                .welcome-section h3 {{
                    color: var(--text-primary);
                    font-size: 1.125rem;
                    font-weight: 600;
                    margin-bottom: 0.5rem;
                }}
                
                .welcome-section p {{
                    color: var(--text-secondary);
                    font-size: 0.875rem;
                }}
                
                .otp-section {{
                    background: var(--background-primary);
                    border-radius: 12px;
                    padding: 2rem;
                    box-shadow: var(--shadow-light);
                    border: 1px solid var(--border-light);
                    margin-bottom: 1.5rem;
                    text-align: center;
                }}
                
                .otp-section h3 {{
                    color: var(--text-primary);
                    font-size: 1.125rem;
                    font-weight: 600;
                    margin-bottom: 1rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 0.5rem;
                }}
                
                .otp-code {{
                    background: linear-gradient(135deg, var(--primary-red), var(--secondary-red));
                    color: white;
                    font-size: 2.5rem;
                    font-weight: 800;
                    letter-spacing: 0.5rem;
                    padding: 1.5rem;
                    border-radius: 12px;
                    margin: 1rem 0;
                    display: inline-block;
                    box-shadow: var(--shadow-medium);
                }}
                
                .otp-description {{
                    color: var(--text-secondary);
                    font-size: 0.875rem;
                    margin-top: 1rem;
                }}
                
                .action-section {{
                    background: var(--background-primary);
                    border-radius: 12px;
                    padding: 1.5rem;
                    box-shadow: var(--shadow-light);
                    border: 1px solid var(--border-light);
                    margin-bottom: 1.5rem;
                    text-align: center;
                }}
                
                .action-section h3 {{
                    color: var(--text-primary);
                    font-size: 1.125rem;
                    font-weight: 600;
                    margin-bottom: 1rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 0.5rem;
                }}
                
                .btn-primary {{
                    display: inline-block;
                    background: var(--primary-red);
                    color: white;
                    padding: 0.75rem 1.5rem;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 0.875rem;
                    transition: all 0.2s ease;
                    margin: 0.5rem 0;
                }}
                
                .btn-primary:hover {{
                    background: #b91c1c;
                    transform: translateY(-1px);
                }}
                
                .setup-link {{
                    color: var(--text-muted);
                    font-size: 0.75rem;
                    margin-top: 1rem;
                    word-break: break-all;
                }}
                
                .info-section {{
                    background: var(--background-primary);
                    border-radius: 12px;
                    padding: 1.5rem;
                    box-shadow: var(--shadow-light);
                    border: 1px solid var(--border-light);
                    margin-bottom: 1.5rem;
                }}
                
                .info-section h4 {{
                    color: var(--text-primary);
                    font-size: 1rem;
                    font-weight: 600;
                    margin-bottom: 1rem;
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                }}
                
                .info-section ol {{
                    color: var(--text-secondary);
                    font-size: 0.875rem;
                    padding-left: 1.5rem;
                }}
                
                .info-section li {{
                    margin-bottom: 0.5rem;
                }}
                
                .info-section strong {{
                    color: var(--text-primary);
                    font-weight: 600;
                }}
                
                .warning-section {{
                    background: #fef3c7;
                    border-radius: 12px;
                    padding: 1.5rem;
                    box-shadow: var(--shadow-light);
                    border: 1px solid #f59e0b;
                    margin-bottom: 1.5rem;
                }}
                
                .warning-section h4 {{
                    color: #92400e;
                    font-size: 1rem;
                    font-weight: 600;
                    margin-bottom: 1rem;
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                }}
                
                .warning-section ul {{
                    color: #92400e;
                    font-size: 0.875rem;
                    padding-left: 1.5rem;
                }}
                
                .warning-section li {{
                    margin-bottom: 0.5rem;
                }}
                
                .email-footer {{
                    background: var(--background-gray);
                    padding: 1.5rem;
                    text-align: center;
                    border-top: 1px solid var(--border-light);
                }}
                
                .email-footer p {{
                    color: var(--text-muted);
                    font-size: 0.75rem;
                    margin-bottom: 0.5rem;
                }}
                
                .project-badge {{
                    background: var(--primary-red);
                    color: white;
                    padding: 0.25rem 0.75rem;
                    border-radius: 20px;
                    font-size: 0.75rem;
                    font-weight: 500;
                    display: inline-block;
                    margin-left: 0.5rem;
                }}
                
                @media (max-width: 600px) {{
                    .email-container {{
                        margin: 0;
                        border-radius: 0;
                    }}
                    
                    .email-header,
                    .email-content {{
                        padding: 1rem;
                    }}
                    
                    .otp-code {{
                        font-size: 2rem;
                        letter-spacing: 0.25rem;
                        padding: 1rem;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="email-header">
                    <h1>
                        <span>🔐</span>
                        Set Your Password
                    </h1>
                    <div class="subtitle">Welcome to the {project_name} project!</div>
                </div>
                
                <div class="email-content">
                    <div class="welcome-section">
                        <h3>Hello {client_username}!</h3>
                        <p>You've been invited to access the <strong>{project_name}</strong> project. To get started, you need to set up your password using the OTP (One-Time Password) below.</p>
                    </div>
                    
                    <div class="otp-section">
                        <h3>
                            <span>🔑</span>
                            Your OTP Code
                        </h3>
                        <div class="otp-code">{otp}</div>
                        <div class="otp-description">Enter this code to set your password</div>
                    </div>
                    
                    <div class="action-section">
                        <h3>
                            <span>🚀</span>
                            Quick Setup
                        </h3>
                        <p style="color: var(--text-secondary); margin-bottom: 1rem;">Click the button below to set your password directly:</p>
                        <a href="{setup_url}" class="btn-primary">Set My Password Now</a>
                        <div class="setup-link">Or copy and paste this link: {setup_url}</div>
                    </div>
                    
                    <div class="warning-section">
                        <h4>
                            <span>⚠️</span>
                            Important Security Notes
                        </h4>
                        <ul>
                            <li>This OTP will expire in 10 minutes</li>
                            <li>Do not share this code with anyone</li>
                            <li>If you didn't request this, please ignore this email</li>
                        </ul>
                    </div>
                    
                    <div class="info-section">
                        <h4>
                            <span>📋</span>
                            Next Steps
                        </h4>
                        <ol>
                            <li>Click the "Set My Password Now" button above</li>
                            <li>Enter your username: <strong>{client_username}</strong></li>
                            <li>Enter the OTP code: <strong>{otp}</strong></li>
                            <li>Set your new password</li>
                            <li><strong>Login with this password</strong> to access your project</li>
                        </ol>
                    </div>
                </div>
                
                <div class="email-footer">
                    <p>This is an automated message from the E-Click Project Management System.</p>
                    <p>If you have any questions, please contact your project administrator.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def _create_simple_otp_text(self, otp, client_username, project_name, site_url=None):
        """Create simple text OTP email"""
        from urllib.parse import quote
        encoded_username = quote(client_username)
        setup_url = f"{site_url}/client/setup-password/?username={encoded_username}" if site_url else f"/client/setup-password/?username={encoded_username}"
        
        text_body = f"""
Welcome to the {project_name} project!

Your username: {client_username}

To set your password, please use the following OTP code:
{otp}

This OTP will expire in 10 minutes.

You can set your password by visiting:
{setup_url}

If you didn't request this, please ignore this email.

Best regards,
E-Click Team
        """
        
        return text_body.strip()
    
    def _create_simple_user_otp_text(self, otp, username, site_url=None):
        """Create simple text OTP email for users"""
        from urllib.parse import quote
        encoded_username = quote(username)
        setup_url = f"{site_url}/user/setup-password/?username={encoded_username}" if site_url else f"/user/setup-password/?username={encoded_username}"
        
        text_body = f"""
Welcome to E-Click!

Your username: {username}

To set your password, please use the following OTP code:
{otp}

This OTP will expire in 10 minutes.

You can set your password by visiting:
{setup_url}

If you didn't request this, please ignore this email.

Best regards,
E-Click Team
        """
        
        return text_body.strip()
    
    def _create_simple_password_reset_otp_text(self, otp, username, site_url=None):
        """Create simple text OTP email for password reset"""
        from urllib.parse import quote
        encoded_username = quote(username)
        reset_url = f"{site_url}/user/reset-password/?username={encoded_username}" if site_url else f"/user/reset-password/?username={encoded_username}"
        
        text_body = f"""
Password Reset Request - E-Click

Your username: {username}

An administrator has requested a password reset for your account.

To reset your password, please use the following OTP code:
{otp}

This OTP will expire in 10 minutes.

You can reset your password by visiting:
{reset_url}

IMPORTANT: Click on the link above or copy and paste it into your web browser.

If you didn't request this password reset, please contact your administrator immediately.

Best regards,
E-Click Team
        """
        
        return text_body.strip()

    def send_email(self, to_email, subject, body, from_email=None, attachments=None):
        """
        Send email using Django's built-in email functionality
        
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
            # Determine if body is HTML
            is_html = '<html>' in body.lower() or '<body>' in body.lower() or '<div>' in body.lower()
            
            # Use EmailMessage for better control
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=from_email or self.from_email,
                to=[to_email]
            )
            
            # Set content type
            if is_html:
                email.content_subtype = "html"
                self.logger.info("Email will be sent as HTML")
            else:
                self.logger.info("Email will be sent as plain text")
            
            # Add attachments if provided
            if attachments:
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        file_size = os.path.getsize(attachment_path)
                        self.logger.info(f"Attaching file: {attachment_path} ({file_size} bytes)")
                        
                        with open(attachment_path, 'rb') as f:
                            email.attach(
                                filename=os.path.basename(attachment_path),
                                content=f.read()
                            )
                        self.logger.info(f"Successfully attached: {os.path.basename(attachment_path)}")
                    else:
                        self.logger.error(f"Attachment file not found: {attachment_path}")
            else:
                self.logger.info("No attachments to add")
            
            # Send the email
            email.send()
            
            self.logger.info(f"Email sent successfully to {to_email}")
            return {
                'success': True,
                'message': 'Email sent successfully'
            }
            
        except Exception as e:
            self.logger.error(f"Error sending email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending email: {str(e)}'
            }
    
    def send_report_email(self, to_email, report_data, custom_message=''):
        """
        Send a PDF report email with attachment using the exact same PDF as the reports view
        
        Args:
            to_email (str): Recipient email address
            report_data (dict): Report data containing statistics
            custom_message (str): Custom message to include
        
        Returns:
            dict: Response with success status and message
        """
        try:
            # Import the exact PDF generation function from views
            from .views import generate_exact_pdf_report
            
            # Generate the exact same PDF as the reports view
            pdf_file = generate_exact_pdf_report(days_filter=report_data.get('days_filter', 30))
            
            # Verify PDF was created and has content
            if not os.path.exists(pdf_file):
                raise Exception("PDF file was not created")
            
            file_size = os.path.getsize(pdf_file)
            if file_size == 0:
                raise Exception("PDF file is empty")
            
            self.logger.info(f"PDF generated successfully: {pdf_file} ({file_size} bytes)")
            
            # Create HTML email body instead of plain text
            email_body = self._create_report_html(report_data, custom_message)
            
            subject = f"E-Click Project Management Report - {report_data.get('date_range', 'Recent Period')}"
            
            # Send email with PDF attachment
            result = self.send_email(
                to_email=to_email,
                subject=subject,
                body=email_body,
                from_email=None,  # Will use OAuth2 account email,
                attachments=[pdf_file]
            )
            
            # Clean up the temporary PDF file
            try:
                os.unlink(pdf_file)
                self.logger.info("PDF file cleaned up successfully")
            except Exception as cleanup_error:
                self.logger.warning(f"Failed to clean up PDF file: {cleanup_error}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error sending report email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending report email: {str(e)}'
            }
    
    def send_project_report_email(self, to_email, report_data, custom_message=''):
        """
        Send a project-specific PDF report email with attachment using the exact same PDF as the reports view
        
        Args:
            to_email (str): Recipient email address
            report_data (dict): Project-specific report data containing statistics
            custom_message (str): Custom message to include
        
        Returns:
            dict: Response with success status and message
        """
        try:
            # Import the exact PDF generation function from views
            from .views import generate_project_specific_pdf_report
            
            # Generate the exact same PDF as the reports view but for specific project
            pdf_file = generate_project_specific_pdf_report(
                project_id=report_data.get('project_id'),
                days_filter=report_data.get('days_filter', 30)
            )
            
            # Create email body text
            email_body = self._create_project_email_body(report_data, custom_message)
            
            subject = f"Project Report: {report_data.get('project_name', 'Project')} - {report_data.get('generated_date', 'Recent Period')}"
            
            # Send email with PDF attachment
            result = self.send_email(
                to_email=to_email,
                subject=subject,
                body=email_body,
                from_email=None,  # Will use OAuth2 account email,
                attachments=[pdf_file]
            )
            
            # Clean up the temporary PDF file
            try:
                import os
                os.remove(pdf_file)
                self.logger.info(f"Cleaned up temporary PDF file: {pdf_file}")
            except Exception as e:
                self.logger.warning(f"Could not clean up temporary PDF file {pdf_file}: {str(e)}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error sending project report email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending project report email: {str(e)}'
            }

    def send_client_report_email(self, to_email, report_data):
        """
        Send a client-specific PDF report email with attachment
        
        Args:
            to_email (str): Recipient email address
            report_data (dict): Client-specific report data containing statistics
        
        Returns:
            dict: Response with success status and message
        """
        try:
            # Import the PDF generation function
            from .views import generate_client_specific_pdf_report
            
            # Generate PDF report
            client_id = report_data.get('client_id')
            if not client_id:
                return {
                    'success': False,
                    'error': 'Client ID is required for PDF generation'
                }
            
            # Generate the PDF
            pdf_path = generate_client_specific_pdf_report(client_id, days_filter=30)
            
            # Check if PDF was generated successfully
            import os
            if not os.path.exists(pdf_path):
                return {
                    'success': False,
                    'error': 'Failed to generate PDF report'
                }
            
            # Get PDF file size for logging
            pdf_size = os.path.getsize(pdf_path)
            self.logger.info(f"Generated client PDF report: {pdf_path}, size: {pdf_size} bytes")
            
            # Create email body text
            email_body = self._create_client_email_body(report_data)
            
            subject = f"Client Report: {report_data.get('client_name', 'Client')} - {report_data.get('generated_date', 'Recent Period')}"
            
            # Send email with PDF attachment
            result = self.send_email(
                to_email=to_email,
                subject=subject,
                body=email_body,
                from_email=None,  # Will use OAuth2 account email,
                attachments=[pdf_path]  # Pass the file path directly
            )
            
            # Clean up the temporary PDF file
            try:
                os.remove(pdf_path)
                self.logger.info(f"Cleaned up temporary PDF file: {pdf_path}")
            except Exception as e:
                self.logger.warning(f"Could not clean up temporary PDF file {pdf_path}: {str(e)}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error sending client report email: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending client report email: {str(e)}'
            }

    def send_weekly_client_report(self, client_email, client_username, report_data, site_url=None):
        """
        Send weekly client report email
        
        Args:
            client_email (str): Client's email address
            client_username (str): Client's username
            report_data (dict): Weekly report data
            site_url (str): Base URL of the site for creating links
        
        Returns:
            dict: Response with success status and message
        """
        try:
            subject = f"Weekly Project Report - {client_username}"
            
            # Create HTML email body
            html_body = self._create_weekly_client_report_html(client_username, report_data, site_url)
            
            # Create plain text email body
            text_body = self._create_weekly_client_report_text(client_username, report_data, site_url)
            
            # Send email as HTML with text fallback
            email = EmailMessage(
                subject=subject,
                body=html_body,
                from_email=self.from_email,
                to=[client_email]
            )
            email.content_subtype = "html"
            
            email.send()
            
            self.logger.info(f"Weekly client report sent successfully to {client_email}")
            return {
                'success': True,
                'message': 'Weekly client report sent successfully'
            }
            
        except Exception as e:
            self.logger.error(f"Error sending weekly client report: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending weekly client report: {str(e)}'
            }

    def send_friday_client_report(self, client_email, client_username, report_data, site_url=None):
        """
        Send Friday client report email
        
        Args:
            client_email (str): Client's email address
            client_username (str): Client's username
            report_data (dict): Friday report data
            site_url (str): Base URL of the site for creating links
        
        Returns:
            dict: Response with success status and message
        """
        try:
            subject = f"Friday Project Report - {client_username} - {report_data.get('report_date', '')}"
            
            # Create HTML email body
            html_body = self._create_friday_client_report_html(client_username, report_data, site_url)
            
            # Create plain text email body
            text_body = self._create_friday_client_report_text(client_username, report_data, site_url)
            
            # Send email as HTML with text fallback
            email = EmailMessage(
                subject=subject,
                body=html_body,
                from_email=self.from_email,
                to=[client_email]
            )
            email.content_subtype = "html"
            
            email.send()
            
            self.logger.info(f"Friday client report sent successfully to {client_email}")
            return {
                'success': True,
                'message': 'Friday client report sent successfully'
            }
            
        except Exception as e:
            self.logger.error(f"Error sending Friday client report: {str(e)}")
            return {
                'success': False,
                'error': f'Error sending Friday client report: {str(e)}'
            }

    def _create_client_email_body(self, report_data):
        """
        Create email body for client reports
        """
        client_name = report_data.get('client_name', 'Client')
        total_projects = report_data.get('total_projects', 0)
        completed_projects = report_data.get('completed_projects', 0)
        in_progress_projects = report_data.get('in_progress_projects', 0)
        planned_projects = report_data.get('planned_projects', 0)
        total_tasks = report_data.get('total_tasks', 0)
        completed_tasks = report_data.get('completed_tasks', 0)
        in_progress_tasks = report_data.get('in_progress_tasks', 0)
        project_completion_rate = report_data.get('project_completion_rate', 0)
        task_completion_rate = report_data.get('task_completion_rate', 0)
        generated_date = report_data.get('generated_date', '')
        
        # Calculate percentages
        project_completion_pct = (completed_projects / total_projects * 100) if total_projects > 0 else 0
        task_completion_pct = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        email_body = f"""
Dear {client_name},

Thank you for choosing E-Click for your project management needs. Here is your comprehensive client report:

**Project Overview:**
• Total Projects: {total_projects}
• Completed Projects: {completed_projects} ({project_completion_pct:.1f}%)
• In Progress Projects: {in_progress_projects}
• Planned Projects: {planned_projects}

**Task Summary:**
• Total Tasks: {total_tasks}
• Completed Tasks: {completed_tasks} ({task_completion_pct:.1f}%)
• In Progress Tasks: {in_progress_tasks}

**Performance Metrics:**
• Project Completion Rate: {project_completion_rate:.1f}%
• Task Completion Rate: {task_completion_rate:.1f}%

**Recent Activity:**
Your projects are being actively managed and monitored. Our team is committed to delivering high-quality results and maintaining clear communication throughout the project lifecycle.

**Next Steps:**
We will continue to provide regular updates and ensure all projects meet their objectives. If you have any questions or need additional information, please don't hesitate to contact us.

Best regards,
The E-Click Team

---
Generated on {generated_date}
E-Click Project Management System

📎 **PDF Report Attached** - Please check your email attachments for a detailed PDF version of this report.
        """
        
        return email_body.strip()
    
    def _create_report_html(self, report_data, custom_message):
        """Create a clean, simple text email body for general reports"""
        body = f"""
Dear Team,

Please find attached the E-Click Project Management Report covering {report_data.get('date_range', 'the recent period')}.

📊 Executive Summary:
• Total Projects: {report_data.get('total_projects', 0)}
• Projects Completed: {report_data.get('projects_completed', 0)}
• Projects In Progress: {report_data.get('projects_in_progress', 0)}
• Projects Planned: {report_data.get('projects_planned', 0)}

📈 Performance Metrics:
• Project Completion Rate: {report_data.get('project_completion_rate', 0):.1f}%
• Task Completion Rate: {report_data.get('task_completion_rate', 0):.1f}%
• User Engagement Rate: {report_data.get('user_engagement_rate', 0):.1f}%

📋 Task Overview:
• Total Tasks: {report_data.get('total_tasks', 0)}
• Completed Tasks: {report_data.get('completed_tasks', 0)}
• Tasks In Progress: {report_data.get('in_progress_tasks', 0)}
• Tasks Not Started: {report_data.get('not_started_tasks', 0)}

👥 Team Activity:
• Total Users: {report_data.get('total_users', 0)}
• Active Users: {report_data.get('active_users', 0)}

{f"💬 Custom Message: {custom_message}" if custom_message else ""}

📎 **PDF Report Attached** - A detailed PDF report is attached to this email for your review.

The PDF report includes:
• Comprehensive project analysis
• Detailed task breakdowns
• Performance insights and trends
• Strategic recommendations
• User activity summaries

Please let me know if you have any questions or need additional information.

Best regards,
E-Click Project Management Team

---
Generated on: {report_data.get('generated_date', 'Recent')}
        """
        return body.strip()
    
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
    
    def _create_email_body(self, report_data, custom_message):
        """Create a nice text email body"""
        body = f"""
Dear Team,

I hope this email finds you well. Please find attached the E-Click Project Management Report for {report_data.get('date_range', 'the recent period')}.

📊 Report Summary:
• Total Projects: {report_data.get('total_projects', 0)}
• Completed Projects: {report_data.get('projects_completed', 0)}
• Projects in Progress: {report_data.get('projects_in_progress', 0)}
• Total Tasks: {report_data.get('total_tasks', 0)}
• Completed Tasks: {report_data.get('completed_tasks', 0)}
• Active Users: {report_data.get('active_users', 0)} out of {report_data.get('total_users', 0)}

📈 Key Performance Metrics:
• Project Completion Rate: {report_data.get('project_completion_rate', 0):.1f}%
• Task Completion Rate: {report_data.get('task_completion_rate', 0):.1f}%
• User Engagement Rate: {report_data.get('user_engagement_rate', 0):.1f}%

{f"💬 Custom Message: {custom_message}" if custom_message else ""}

The detailed PDF report is attached to this email for your review. Please let me know if you have any questions or need additional information.

Best regards,
E-Click Project Management System

---
Generated on: {report_data.get('generated_date', 'Recent')}
        """
        return body.strip()

    def _create_project_email_body(self, report_data, custom_message):
        """Create a nice text email body for project-specific reports"""
        body = f"""
Dear {report_data.get('client_name', 'Client')},

I hope this email finds you well. Please find attached the detailed project report for "{report_data.get('project_name', 'your project')}" covering {report_data.get('date_range', 'the recent period')}.

📊 Project Summary:
• Project Name: {report_data.get('project_name', 'N/A')}
• Project Status: {report_data.get('project_status', 'N/A')}
• Project Duration: {report_data.get('project_duration', 'Not set')}
• Total Tasks: {report_data.get('total_tasks', 0)}
• Completed Tasks: {report_data.get('completed_tasks', 0)}
• Tasks In Progress: {report_data.get('in_progress_tasks', 0)}

📈 Key Performance Metrics:
• Task Completion Rate: {report_data.get('task_completion_rate', 0):.1f}%
• SubTask Completion Rate: {report_data.get('subtask_completion_rate', 0):.1f}%

{f"💬 Custom Message: {custom_message}" if custom_message else ""}

The detailed PDF report is attached to this email for your review. This report includes:
• Project overview and current status
• Task progress summary with completion rates
• Recent activity and milestones
• Project insights and recommendations
• Timeline analysis and progress tracking

Please let me know if you have any questions or need additional information about the project progress.

Best regards,
E-Click Project Management Team

---
Generated on: {report_data.get('generated_date', 'Recent')}

📎 **PDF Report Attached** - Please check your email attachments for a detailed PDF version of this project report.
        """
        return body.strip()

    def _create_weekly_client_report_html(self, client_username, report_data, site_url=None):
        """Create HTML body for weekly client report"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Weekly Project Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px; margin-bottom: 30px; }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
                .section {{ background: #f8f9fa; padding: 20px; margin-bottom: 20px; border-radius: 8px; border-left: 4px solid #667eea; }}
                .section h2 {{ margin: 0 0 15px 0; color: #667eea; font-size: 20px; }}
                .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px; }}
                .metric-card {{ background: white; padding: 15px; border-radius: 6px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #667eea; margin-bottom: 5px; }}
                .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
                .project-item {{ background: white; padding: 15px; margin-bottom: 10px; border-radius: 6px; border-left: 3px solid #10b981; }}
                .project-name {{ font-weight: bold; margin-bottom: 5px; }}
                .project-status {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
                .status-completed {{ background: #d1fae5; color: #065f46; }}
                .status-in_progress {{ background: #dbeafe; color: #1e40af; }}
                .status-planned {{ background: #f3e8ff; color: #7c3aed; }}
                .task-list {{ margin-top: 10px; }}
                .task-item {{ padding: 5px 0; border-bottom: 1px solid #eee; }}
                .task-item:last-child {{ border-bottom: none; }}
                .task-title {{ font-weight: 500; }}
                .task-status {{ font-size: 12px; color: #666; }}
                .footer {{ text-align: center; margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px; }}
                .footer a {{ color: #667eea; text-decoration: none; }}
                .footer a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 Weekly Project Report</h1>
                <p>Hello {client_username}, here's your weekly project update</p>
            </div>
            
            <div class="section">
                <h2>📈 Weekly Summary</h2>
                <div class="metric-grid">
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('total_projects', 0)}</div>
                        <div class="metric-label">Total Projects</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('active_projects', 0)}</div>
                        <div class="metric-label">Active Projects</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('completed_projects', 0)}</div>
                        <div class="metric-label">Completed</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('total_tasks', 0)}</div>
                        <div class="metric-label">Total Tasks</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>🚀 Project Updates</h2>
                {self._generate_project_updates_html(report_data.get('projects', []))}
            </div>
            
            <div class="section">
                <h2>📋 Recent Task Activity</h2>
                {self._generate_task_activity_html(report_data.get('recent_tasks', []))}
            </div>
            
            <div class="footer">
                <p>This report was automatically generated by E-Click</p>
                <p><a href="{site_url or '#'}">View your projects online</a></p>
                <p style="font-size: 12px; color: #666;">Report generated on {report_data.get('report_date', 'N/A')}</p>
            </div>
        </body>
        </html>
        """
        return html_content

    def _create_weekly_client_report_text(self, client_username, report_data, site_url=None):
        """Create plain text body for weekly client report"""
        text_content = f"""
Weekly Project Report - {client_username}

Hello {client_username},

Here's your weekly project update from E-Click:

WEEKLY SUMMARY:
- Total Projects: {report_data.get('total_projects', 0)}
- Active Projects: {report_data.get('active_projects', 0)}
- Completed Projects: {report_data.get('completed_projects', 0)}
- Total Tasks: {report_data.get('total_tasks', 0)}

PROJECT UPDATES:
{self._generate_project_updates_text(report_data.get('projects', []))}

RECENT TASK ACTIVITY:
{self._generate_task_activity_text(report_data.get('recent_tasks', []))}

View your projects online: {site_url or 'N/A'}

This report was automatically generated by E-Click on {report_data.get('report_date', 'N/A')}.

Best regards,
E-Click Team
        """
        return text_content

    def _create_friday_client_report_html(self, client_username, report_data, site_url=None):
        """Create HTML body for Friday client report"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Friday Project Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 30px; text-align: center; border-radius: 10px; margin-bottom: 30px; }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
                .section {{ background: #f8f9fa; padding: 20px; margin-bottom: 20px; border-radius: 8px; border-left: 4px solid #f59e0b; }}
                .section h2 {{ margin: 0 0 15px 0; color: #f59e0b; font-size: 20px; }}
                .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px; }}
                .metric-card {{ background: white; padding: 15px; border-radius: 6px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #f59e0b; margin-bottom: 5px; }}
                .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
                .project-item {{ background: white; padding: 15px; margin-bottom: 10px; border-radius: 6px; border-left: 3px solid #10b981; }}
                .project-name {{ font-weight: bold; margin-bottom: 5px; }}
                .project-status {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
                .status-completed {{ background: #d1fae5; color: #065f46; }}
                .status-in_progress {{ background: #dbeafe; color: #1e40af; }}
                .status-planned {{ background: #f3e8ff; color: #7c3aed; }}
                .task-list {{ margin-top: 10px; }}
                .task-item {{ padding: 5px 0; border-bottom: 1px solid #eee; }}
                .task-item:last-child {{ border-bottom: none; }}
                .task-title {{ font-weight: 500; }}
                .task-status {{ font-size: 12px; color: #666; }}
                .deadline-warning {{ background: #fef3c7; border: 1px solid #f59e0b; padding: 10px; border-radius: 6px; margin: 10px 0; }}
                .deadline-urgent {{ background: #fee2e2; border: 1px solid #ef4444; padding: 10px; border-radius: 6px; margin: 10px 0; }}
                .footer {{ text-align: center; margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px; }}
                .footer a {{ color: #f59e0b; text-decoration: none; }}
                .footer a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 Friday Project Report</h1>
                <p>Hello {client_username}, here's your Friday project update</p>
                <p style="font-size: 14px; opacity: 0.8;">Week of {report_data.get('week_range', 'N/A')}</p>
            </div>
            
            <div class="section">
                <h2>📈 Weekly Summary</h2>
                <div class="metric-grid">
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('total_projects', 0)}</div>
                        <div class="metric-label">Total Projects</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('active_projects', 0)}</div>
                        <div class="metric-label">Active Projects</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('completed_projects', 0)}</div>
                        <div class="metric-label">Completed</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('total_tasks', 0)}</div>
                        <div class="metric-label">Total Tasks</div>
                    </div>
                </div>
                
                <div class="metric-grid">
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('project_completion_rate', 0)}%</div>
                        <div class="metric-label">Project Completion</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{report_data.get('task_completion_rate', 0)}%</div>
                        <div class="metric-label">Task Completion</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>🚀 Project Updates</h2>
                {self._generate_project_updates_html(report_data.get('projects', []))}
            </div>
            
            <div class="section">
                <h2>📋 Recent Task Activity</h2>
                {self._generate_task_activity_html(report_data.get('recent_tasks', []))}
            </div>
            
            {self._generate_upcoming_deadlines_html(report_data.get('upcoming_deadlines', []))}
            
            <div class="footer">
                <p>This Friday report was automatically generated by E-Click</p>
                <p><a href="{site_url or '#'}">View your projects online</a></p>
                <p style="font-size: 12px; color: #666;">Report generated on {report_data.get('report_date', 'N/A')}</p>
                <p style="font-size: 12px; color: #666;">Next Friday report: {report_data.get('next_friday', 'N/A')}</p>
            </div>
        </body>
        </html>
        """
        return html_content

    def _create_friday_client_report_text(self, client_username, report_data, site_url=None):
        """Create plain text body for Friday client report"""
        text_content = f"""
Friday Project Report - {client_username}

Hello {client_username},

Here's your Friday project update from E-Click:

WEEKLY SUMMARY:
- Total Projects: {report_data.get('total_projects', 0)}
- Active Projects: {report_data.get('active_projects', 0)}
- Completed Projects: {report_data.get('completed_projects', 0)}
- Planned Projects: {report_data.get('planned_projects', 0)}
- Total Tasks: {report_data.get('total_tasks', 0)}
- Completed Tasks: {report_data.get('completed_tasks', 0)}
- In Progress Tasks: {report_data.get('in_progress_tasks', 0)}

PERFORMANCE METRICS:
- Project Completion Rate: {report_data.get('project_completion_rate', 0)}%
- Task Completion Rate: {report_data.get('task_completion_rate', 0)}%

PROJECT UPDATES:
{self._generate_project_updates_text(report_data.get('projects', []))}

RECENT TASK ACTIVITY:
{self._generate_task_activity_text(report_data.get('recent_tasks', []))}

UPCOMING DEADLINES:
{self._generate_upcoming_deadlines_text(report_data.get('upcoming_deadlines', []))}

This Friday report was automatically generated by E-Click.
Report generated on {report_data.get('report_date', 'N/A')}
Next Friday report: {report_data.get('next_friday', 'N/A')}

Best regards,
The E-Click Team
        """
        return text_content

    def _generate_project_updates_html(self, projects):
        """Generate HTML for project updates section"""
        if not projects:
            return '<p style="color: #666; text-align: center;">No project updates this week</p>'
        
        html = ''
        for project in projects:
            status_class = f"status-{project.get('status', 'planned')}"
            status_text = project.get('status', 'planned').replace('_', ' ').title()
            
            html += f"""
            <div class="project-item">
                <div class="project-name">{project.get('name', 'N/A')}</div>
                <span class="project-status {status_class}">{status_text}</span>
                <div style="margin-top: 10px; font-size: 14px; color: #666;">
                    {project.get('description', 'No description available')}
                </div>
                <div style="margin-top: 10px; font-size: 12px; color: #666;">
                    Progress: {project.get('completion_rate', 0)}% complete
                </div>
            </div>
            """
        return html

    def _generate_project_updates_text(self, projects):
        """Generate plain text for project updates section"""
        if not projects:
            return "No project updates this week"
        
        text = ""
        for project in projects:
            status = project.get('status', 'planned').replace('_', ' ').title()
            text += f"- {project.get('name', 'N/A')} ({status}) - {project.get('completion_rate', 0)}% complete\n"
            text += f"  {project.get('description', 'No description available')}\n\n"
        return text

    def _generate_task_activity_html(self, tasks):
        """Generate HTML for task activity section"""
        if not tasks:
            return '<p style="color: #666; text-align: center;">No recent task activity</p>'
        
        html = ''
        for task in tasks:
            html += f"""
            <div class="task-item">
                <div class="task-title">{task.get('title', 'N/A')}</div>
                <div class="task-status">Status: {task.get('status', 'N/A').replace('_', ' ').title()} | Project: {task.get('project_name', 'N/A')}</div>
            </div>
            """
        return html

    def _generate_task_activity_text(self, tasks):
        """Generate plain text for task activity section"""
        if not tasks:
            return "No recent task activity"
        
        text = ""
        for task in tasks:
            status = task.get('status', 'N/A').replace('_', ' ').title()
            text += f"- {task.get('title', 'N/A')} ({status}) - Project: {task.get('project_name', 'N/A')}\n"
        return text

# Create a global instance
email_service = SimpleEmailService() 