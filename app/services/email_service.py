from flask import current_app
from flask_mail import Message
from app import mail, db
from app.models import EmailLog
from datetime import datetime
import os

class EmailService:
    def __init__(self):
        self.sender_email = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))
    
    def generate_bulletin_email(self, user, items):
        """Generate email content for bulletin items"""
        subject = f"KGV Bulletin - Year {user.year_group} Highlights"
        
        # Generate HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@300;400;500;600;700&family=Red+Hat+Text:wght@300;400;500;600&display=swap" rel="stylesheet">
            <style>
                body {{
                    font-family: 'Red Hat Text', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #111827;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9fafb;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    font-family: 'Red Hat Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-weight: 600;
                }}
                .header {{
                    background: #1f2937;
                    color: white;
                    padding: 30px;
                    border-radius: 8px;
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 600;
                }}
                .header p {{
                    margin: 10px 0 0 0;
                    opacity: 0.9;
                    color: #e5e7eb;
                }}
                .item {{
                    background: white;
                    border-radius: 6px;
                    padding: 25px;
                    margin-bottom: 25px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                    border-left: 4px solid #1f2937;
                }}
                .item-number {{
                    background: #1f2937;
                    color: white;
                    padding: 6px 14px;
                    border-radius: 16px;
                    font-size: 14px;
                    font-weight: 500;
                    display: inline-block;
                    margin-bottom: 15px;
                }}
                .headline {{
                    background: #f3f4f6;
                    border-left: 3px solid #374151;
                    padding: 15px;
                    margin-bottom: 20px;
                    border-radius: 4px;
                }}
                .headline h3 {{
                    margin: 0;
                    color: #374151;
                    font-size: 18px;
                    font-weight: 600;
                }}
                .content {{
                    font-size: 15px;
                    line-height: 1.7;
                    white-space: pre-line;
                    color: #111827;
                }}
                .attachments {{
                    background: #f3f4f6;
                    padding: 15px;
                    border-radius: 4px;
                    margin-top: 15px;
                }}
                .attachments h4 {{
                    margin: 0 0 10px 0;
                    color: #374151;
                    font-size: 14px;
                    font-weight: 500;
                }}
                .attachment-link {{
                    color: #1f2937;
                    text-decoration: none;
                    display: block;
                    margin-bottom: 5px;
                    font-weight: 500;
                }}
                .attachment-link:hover {{
                    text-decoration: underline;
                }}
                .metadata {{
                    font-size: 13px;
                    color: #6b7280;
                    margin-top: 15px;
                    padding-top: 15px;
                    border-top: 1px solid #e5e7eb;
                }}
                .footer {{
                    text-align: center;
                    padding: 30px;
                    background: white;
                    border-radius: 6px;
                    margin-top: 30px;
                    border: 1px solid #e5e7eb;
                }}
                .footer p {{
                    margin: 5px 0;
                    color: #6b7280;
                    font-size: 14px;
                }}
                .unsubscribe {{
                    color: #374151;
                    text-decoration: none;
                    font-size: 12px;
                    font-weight: 500;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>KGV Bulletin Highlights</h1>
                <p>Year {user.year_group} • {datetime.now().strftime('%B %d, %Y')}</p>
            </div>
        """
        
        if not items:
            html_content += """
            <div class="item">
                <p>No new bulletin items found for your year group today.</p>
                <p>Check back tomorrow for updates!</p>
            </div>
            """
        else:
            for i, item in enumerate(items, 1):
                html_content += f"""
                <div class="item">
                    <div class="item-number">Item {i}</div>
                """
                
                if item.ai_headline:
                    html_content += f"""
                    <div class="headline">
                        <h3>{item.ai_headline}</h3>
                    </div>
                    """
                
                html_content += f"""
                    <div class="content">{item.content}</div>
                """
                
                # Add attachments if any
                attachments = item.get_attachments()
                if attachments:
                    html_content += """
                    <div class="attachments">
                        <h4>Attachments:</h4>
                    """
                    for attachment in attachments:
                        html_content += f"""
                        <a href="{attachment.get('url', '#')}" class="attachment-link">
                            {attachment.get('name', 'Attachment')}
                        </a>
                        """
                    html_content += "</div>"
                
                # Add metadata
                metadata = item.get_metadata()
                if metadata.get('posted_info'):
                    html_content += f"""
                    <div class="metadata">
                        {metadata['posted_info']}
                    </div>
                    """
                
                html_content += "</div>"
        
        html_content += f"""
            <div class="footer">
                <p><strong>KGV School Bulletin Email Service</strong></p>
                <p>You're receiving this because you subscribed to {user.email_frequency} bulletin updates.</p>
                <p>
                    <a href="#" class="unsubscribe">Update email preferences</a> |
                    <a href="#" class="unsubscribe">Unsubscribe</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def send_bulletin_email(self, user, items, is_test=False):
        """Send bulletin email to a user"""
        try:
            subject, html_content = self.generate_bulletin_email(user, items)
            
            if is_test:
                subject = f"[TEST] {subject}"
            
            # Create email message
            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_content,
                sender=self.sender_email
            )
            
            # Send email
            mail.send(msg)
            
            # Log the email
            email_log = EmailLog(
                user_id=user.id,
                subject=subject,
                content=html_content,
                status='sent',
                sent_at=datetime.utcnow()
            )
            db.session.add(email_log)
            db.session.commit()
            
            return True
            
        except Exception as e:
            # Log the failed email
            email_log = EmailLog(
                user_id=user.id,
                subject=subject if 'subject' in locals() else 'Failed to generate subject',
                content=html_content if 'html_content' in locals() else 'Failed to generate content',
                status='failed',
                error_message=str(e)
            )
            db.session.add(email_log)
            db.session.commit()
            
            print(f"Failed to send email to {user.email}: {e}")
            return False
    
    def send_custom_email(self, user, subject, content):
        """Send a custom email to a user"""
        try:
            # Create HTML wrapper for custom content
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{subject}</title>
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@300;400;500;600;700&family=Red+Hat+Text:wght@300;400;500;600&display=swap" rel="stylesheet">
                <style>
                    body {{
                        font-family: 'Red Hat Text', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        line-height: 1.6;
                        color: #111827;
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 20px;
                        background-color: #f9fafb;
                    }}
                    h1, h2, h3, h4, h5, h6 {{
                        font-family: 'Red Hat Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        font-weight: 600;
                    }}
                    .content {{
                        background: white;
                        padding: 30px;
                        border-radius: 6px;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                    }}
                    .footer {{
                        text-align: center;
                        padding: 20px;
                        color: #6b7280;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="content">
                    {content}
                </div>
                <div class="footer">
                    <p>KGV School Bulletin Email Service</p>
                </div>
            </body>
            </html>
            """
            
            # Create email message
            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_content,
                sender=self.sender_email
            )
            
            # Send email
            mail.send(msg)
            
            # Log the email
            email_log = EmailLog(
                user_id=user.id,
                subject=subject,
                content=html_content,
                status='sent',
                sent_at=datetime.utcnow()
            )
            db.session.add(email_log)
            db.session.commit()
            
            return True
            
        except Exception as e:
            # Log the failed email
            email_log = EmailLog(
                user_id=user.id,
                subject=subject,
                content=content,
                status='failed',
                error_message=str(e)
            )
            db.session.add(email_log)
            db.session.commit()
            
            print(f"Failed to send custom email to {user.email}: {e}")
            return False
    
    def send_bulk_email(self, users, subject, content):
        """Send bulk email to multiple users"""
        successful_sends = 0
        failed_sends = 0
        
        for user in users:
            try:
                success = self.send_custom_email(user, subject, content)
                if success:
                    successful_sends += 1
                else:
                    failed_sends += 1
            except Exception as e:
                print(f"Failed to send bulk email to {user.email}: {e}")
                failed_sends += 1
        
        return {
            'successful_sends': successful_sends,
            'failed_sends': failed_sends,
            'total_recipients': len(users)
        }
    
    def send_verification_email(self, user, token):
        """Send an email verification link to the user"""
        verify_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/verify-email/{token}"
        subject = "Verify your email address for KGV Bulletin Service"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset='utf-8'>
            <meta name='viewport' content='width=device-width, initial-scale=1.0'>
            <title>{subject}</title>
            <style>
                body {{ font-family: 'Red Hat Text', Arial, sans-serif; background: #f9fafb; color: #111827; padding: 30px; }}
                .container {{ background: #fff; border-radius: 8px; padding: 30px; max-width: 600px; margin: 0 auto; box-shadow: 0 1px 3px rgba(0,0,0,0.07); }}
                .btn {{ display: inline-block; background: #1f2937; color: #fff; padding: 12px 28px; border-radius: 5px; text-decoration: none; font-weight: 600; margin-top: 20px; }}
                .footer {{ margin-top: 30px; color: #6b7280; font-size: 13px; text-align: center; }}
            </style>
        </head>
        <body>
            <div class='container'>
                <h2>Welcome to KGV Bulletin Service!</h2>
                <p>Hi {user.name},</p>
                <p>Thank you for registering. Please verify your email address by clicking the button below:</p>
                <a href='{verify_url}' class='btn'>Verify Email</a>
                <p>If the button doesn't work, copy and paste this link into your browser:</p>
                <p><a href='{verify_url}'>{verify_url}</a></p>
                <div class='footer'>If you did not create an account, you can ignore this email.</div>
            </div>
        </body>
        </html>
        """
        try:
            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_content,
                sender=self.sender_email
            )
            mail.send(msg)
            # Log the email
            email_log = EmailLog(
                user_id=user.id,
                subject=subject,
                content=html_content,
                status='sent',
                sent_at=datetime.utcnow()
            )
            db.session.add(email_log)
            db.session.commit()
            return True
        except Exception as e:
            email_log = EmailLog(
                user_id=user.id,
                subject=subject,
                content=html_content,
                status='failed',
                error_message=str(e)
            )
            db.session.add(email_log)
            db.session.commit()
            print(f"Failed to send verification email to {user.email}: {e}")
            return False
