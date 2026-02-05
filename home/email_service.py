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

            # Send email as plain text with proper headers
            email = EmailMessage(
                subject=subject,
                body=text_body,
                from_email=self.from_email,
                to=[to_email],
                headers={
                    'X-Mailer': 'E-Click Project Management System',
                    'X-Priority': '3',
                    'X-MSMail-Priority': 'Normal',
                    'Importance': 'Normal',
                    'Reply-To': self.from_email,
                    'X-Entity-Ref-ID': f'eclick-otp-{client_username}',
                }
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

            # Send email as plain text with proper headers
            email = EmailMessage(
                subject=subject,
                body=text_body,
                from_email=self.from_email,
                to=[to_email],
                headers={
                    'X-Mailer': 'E-Click Project Management System',
                    'X-Priority': '3',
                    'X-MSMail-Priority': 'Normal',
                    'Importance': 'Normal',
                    'Reply-To': self.from_email,
                    'X-Entity-Ref-ID': f'eclick-user-otp-{username}',
                }
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
            from urllib.parse import quote

            subject = f"Password Reset OTP - E-Click"

            # Create reset URL for clients or users
            encoded_username = quote(username)
            if site_url:
                # Check if it's a client or user based on the context
                # We'll create both URLs and use the appropriate one
                reset_url = f"{site_url}/client/reset-password/?username={encoded_username}"
            else:
                reset_url = f"/client/reset-password/?username={encoded_username}"

            # Create HTML email with clickable link
            html_body = f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p>Hello {username},</p>

    <p>We received a request to reset your E-Click account password.</p>

    <p>To reset your password, please use this verification code:</p>

    <p><strong>Your OTP Code: {otp}</strong></p>

    <p>This code will expire in 24 hours.</p>

    <p><a href="{reset_url}" style="color: #2563eb; text-decoration: none; font-weight: bold;">Reset</a> your password using this link.</p>

    <p>If you did not request this password reset, please contact your administrator immediately.</p>

    <p>Thank you,<br>
    The E-Click Team<br>
    E-Click Project Management</p>
</body>
</html>"""

            # Send email as HTML
            email = EmailMessage(
                subject=subject,
                body=html_body,
                from_email=self.from_email,
                to=[to_email],
                headers={
                    'X-Mailer': 'E-Click Project Management System',
                    'X-Priority': '3',
                    'X-MSMail-Priority': 'Normal',
                    'Importance': 'Normal',
                    'Reply-To': self.from_email,
                    'X-Entity-Ref-ID': f'eclick-reset-otp-{username}',
                }
            )
            email.content_subtype = "html"  # Set content type to HTML

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
        """Create HTML formatted OTP email - Simple and professional"""
        # Create the setup password URL with username parameter (URL encoded)
        from urllib.parse import quote
        encoded_username = quote(client_username)
        setup_url = f"{site_url}/client/setup-password/?username={encoded_username}" if site_url else f"/client/setup-password/?username={encoded_username}"

        html = f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p><strong>Set Your Password - {project_name}</strong></p>

    <p>Hello {client_username},</p>

    <p>You've been invited to access the <strong>{project_name}</strong> project. To get started, you need to set up your password using the OTP (One-Time Password) below.</p>

    <p><strong>Your OTP Code: {otp}</strong></p>

    <p>You can set your password here: {setup_url}</p>

    <p><strong>Important Security Notes:</strong></p>
    <ul>
        <li>This OTP will expire in 24 hours</li>
        <li>Do not share this code with anyone</li>
        <li>If you didn't request this, please ignore this email</li>
    </ul>

    <p><strong>Next Steps:</strong></p>
    <ol>
        <li>Visit the password setup page using the link above</li>
        <li>Enter your username: <strong>{client_username}</strong></li>
        <li>Enter the OTP code: <strong>{otp}</strong></li>
        <li>Set your new password</li>
        <li>Login with this password to access your project</li>
    </ol>

    <hr>
    <p>This is an automated message from the E-Click Project Management System.</p>
    <p>If you have any questions, please contact your project administrator.</p>
</body>
</html>"""
        return html
    
    def _create_simple_otp_text(self, otp, client_username, project_name, site_url=None):
        """Create simple text OTP email"""
        from urllib.parse import quote
        encoded_username = quote(client_username)
        setup_url = f"{site_url}/client/setup-password/?username={encoded_username}" if site_url else f"/client/setup-password/?username={encoded_username}"

        text_body = f"""Hello {client_username},

Welcome to {project_name}.

To access your project portal, please use this verification code:

Your OTP Code: {otp}

This code will expire in 24 hours.

Set up your password here:
{setup_url}

If you did not expect this email, you can safely ignore it.

Thank you,
The E-Click Team
E-Click Project Management
{self.from_email}
        """

        return text_body.strip()
    
    def _create_simple_user_otp_text(self, otp, username, site_url=None):
        """Create simple text OTP email for users"""
        from urllib.parse import quote
        encoded_username = quote(username)
        setup_url = f"{site_url}/user/setup-password/?username={encoded_username}" if site_url else f"/user/setup-password/?username={encoded_username}"

        text_body = f"""Hello {username},

Thank you for joining E-Click Project Management System.

To complete your account setup, please use this verification code:

Your OTP Code: {otp}

This code will expire in 24 hours.

You can set up your password here:
{setup_url}

If you did not request this, you can safely ignore this email.

Thank you,
The E-Click Team
E-Click Project Management
{self.from_email}
        """

        return text_body.strip()
    
    def _create_simple_password_reset_otp_text(self, otp, username, site_url=None):
        """Create simple text OTP email for password reset"""
        from urllib.parse import quote
        encoded_username = quote(username)
        reset_url = f"{site_url}/user/reset-password/?username={encoded_username}" if site_url else f"/user/reset-password/?username={encoded_username}"

        text_body = f"""Hello {username},

We received a request to reset your E-Click account password.

To reset your password, please use this verification code:

Your OTP Code: {otp}

This code will expire in 24 hours.

Reset your password here:
{reset_url}

If you did not request this password reset, please contact your administrator immediately.

Thank you,
The E-Click Team
E-Click Project Management
{self.from_email}
        """

        return text_body.strip()

    def send_email(self, to_email, subject, body, from_email=None, attachments=None, cc_emails=None):
        """
        Send email using Django's built-in email functionality

        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            body (str): Email body (HTML or plain text)
            from_email (str): Sender email (optional, uses default if not provided)
            attachments (list): List of attachment file paths (optional)
            cc_emails (list): List of CC email addresses (optional)

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
                to=[to_email],
                headers={
                    'X-Mailer': 'E-Click Project Management System',
                    'X-Priority': '3',
                    'X-MSMail-Priority': 'Normal',
                    'Importance': 'Normal',
                    'Reply-To': self.from_email,
                }
            )

            # Add CC emails if provided
            if cc_emails:
                email.cc = cc_emails
                self.logger.info(f"Adding CC emails: {cc_emails}")

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
            if cc_emails:
                self.logger.info(f"Email CC'd to: {cc_emails}")
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
            # Import the HTML PDF generation function from views (uses WeasyPrint for better layout)
            from .views import generate_html_pdf_report

            # Generate professional HTML-based PDF with guaranteed beautiful layout
            pdf_file = generate_html_pdf_report(days_filter=report_data.get('days_filter', 30))
            
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
        """Create a clean, simple text email body for general reports - Simple and professional"""
        body = f"""
Dear Team,

Please find attached the E-Click Project Management Report covering {report_data.get('date_range', 'the recent period')}.

Executive Summary:
• Total Projects: {report_data.get('total_projects', 0)}
• Projects Completed: {report_data.get('projects_completed', 0)}
• Projects In Progress: {report_data.get('projects_in_progress', 0)}
• Projects Planned: {report_data.get('projects_planned', 0)}

Performance Metrics:
• Project Completion Rate: {report_data.get('project_completion_rate', 0):.1f}%
• Task Completion Rate: {report_data.get('task_completion_rate', 0):.1f}%
• User Engagement Rate: {report_data.get('user_engagement_rate', 0):.1f}%

Task Overview:
• Total Tasks: {report_data.get('total_tasks', 0)}
• Completed Tasks: {report_data.get('completed_tasks', 0)}
• Tasks In Progress: {report_data.get('in_progress_tasks', 0)}
• Tasks Not Started: {report_data.get('not_started_tasks', 0)}

Team Activity:
• Total Users: {report_data.get('total_users', 0)}
• Active Users: {report_data.get('active_users', 0)}

{f"Custom Message: {custom_message}" if custom_message else ""}

PDF Report Attached - A detailed PDF report is attached to this email for your review.

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
        """Create HTML body for weekly client report - Simple and professional"""
        html_content = f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p><strong>Weekly Project Report</strong></p>
    <p>Hello {client_username}, here's your weekly project update</p>

    <p><strong>Weekly Summary:</strong></p>
    <p>Total Projects: {report_data.get('total_projects', 0)}</p>
    <p>Active Projects: {report_data.get('active_projects', 0)}</p>
    <p>Completed: {report_data.get('completed_projects', 0)}</p>
    <p>Total Tasks: {report_data.get('total_tasks', 0)}</p>

    <p><strong>Project Updates:</strong></p>
    {self._generate_project_updates_html(report_data.get('projects', []))}

    <p><strong>Recent Task Activity:</strong></p>
    {self._generate_task_activity_html(report_data.get('recent_tasks', []))}

    <hr>
    <p>This report was automatically generated by E-Click</p>
    <p>View your projects online: {site_url or 'N/A'}</p>
    <p>Report generated on {report_data.get('report_date', 'N/A')}</p>
</body>
</html>"""
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
        """Create HTML body for Friday client report - Simple and professional"""
        html_content = f"""<html>
<body style="font-family: Arial, sans-serif;">
    <p><strong>Friday Project Report</strong></p>
    <p>Hello {client_username}, here's your Friday project update</p>
    <p>Week of {report_data.get('week_range', 'N/A')}</p>

    <p><strong>Weekly Summary:</strong></p>
    <p>Total Projects: {report_data.get('total_projects', 0)}</p>
    <p>Active Projects: {report_data.get('active_projects', 0)}</p>
    <p>Completed: {report_data.get('completed_projects', 0)}</p>
    <p>Total Tasks: {report_data.get('total_tasks', 0)}</p>
    <p>Project Completion: {report_data.get('project_completion_rate', 0)}%</p>
    <p>Task Completion: {report_data.get('task_completion_rate', 0)}%</p>

    <p><strong>Project Updates:</strong></p>
    {self._generate_project_updates_html(report_data.get('projects', []))}

    <p><strong>Recent Task Activity:</strong></p>
    {self._generate_task_activity_html(report_data.get('recent_tasks', []))}

    {self._generate_upcoming_deadlines_html(report_data.get('upcoming_deadlines', []))}

    <hr>
    <p>This Friday report was automatically generated by E-Click</p>
    <p>View your projects online: {site_url or 'N/A'}</p>
    <p>Report generated on {report_data.get('report_date', 'N/A')}</p>
    <p>Next Friday report: {report_data.get('next_friday', 'N/A')}</p>
</body>
</html>"""
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
        """Generate HTML for project updates section - Simple and professional"""
        if not projects:
            return '<p>No project updates this week</p>'

        html = ''
        for project in projects:
            status_text = project.get('status', 'planned').replace('_', ' ').title()
            html += f"""<p><strong>{project.get('name', 'N/A')}</strong> ({status_text})<br>
{project.get('description', 'No description available')}<br>
Progress: {project.get('completion_rate', 0)}% complete</p>"""
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
        """Generate HTML for task activity section - Simple and professional"""
        if not tasks:
            return '<p>No recent task activity</p>'

        html = ''
        for task in tasks:
            html += f"""<p><strong>{task.get('title', 'N/A')}</strong><br>
Status: {task.get('status', 'N/A').replace('_', ' ').title()} | Project: {task.get('project_name', 'N/A')}</p>"""
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