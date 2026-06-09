"""Daily analytics email report generator and sender."""

import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from jobcli.profile.schemas import ApplicationStatus
from jobcli.storage.models import JobModel
from jobcli.storage.repositories import AnalyticsEventRepository, JobRepository


def get_submitted_jobs_last_24h(session: Session):
    """Get jobs submitted in the last 24 hours."""
    since = datetime.now() - timedelta(hours=24)
    return (
        session.query(JobModel)
        .filter(
            JobModel.status == ApplicationStatus.SUBMITTED,
            JobModel.updated_at >= since,
        )
        .all()
    )


def build_email_html(metrics: dict) -> str:
    """Build the HTML content for the email."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1A202C; color: #E2E8F0; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #2D3748; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }}
            .header {{ background: linear-gradient(135deg, #667EEA 0%, #764BA2 100%); padding: 30px 20px; text-align: center; }}
            .header h1 {{ margin: 0; color: #FFFFFF; font-size: 24px; font-weight: 600; }}
            .content {{ padding: 30px; background-color: #1A202C; }}
            .metric-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }}
            .metric-card {{ background: #2D3748; padding: 20px; border-radius: 10px; text-align: center; border: 1px solid #4A5568; }}
            .metric-value {{ font-size: 32px; font-weight: bold; color: #63B3ED; margin: 10px 0 5px 0; }}
            .metric-label {{ font-size: 14px; color: #A0AEC0; text-transform: uppercase; letter-spacing: 0.05em; }}
            .section-title {{ font-size: 18px; font-weight: 600; color: #E2E8F0; margin-bottom: 15px; border-bottom: 1px solid #4A5568; padding-bottom: 10px; margin-top: 30px; }}
            .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #718096; border-top: 1px solid #2D3748; }}
            
            /* Table Styles */
            .user-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; background-color: #313D50; border-radius: 6px; overflow: hidden; }}
            .user-table th {{ background-color: #4A5568; color: #E2E8F0; font-weight: 600; padding: 12px 15px; text-align: left; font-size: 14px; }}
            .user-table td {{ padding: 12px 15px; border-bottom: 1px solid #4A5568; font-size: 14px; color: #E2E8F0; }}
            .user-table tr:last-child td {{ border-bottom: none; }}
            .user-table tbody tr:hover {{ background-color: #2D3748; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Wbox Platform Daily Report</h1>
            </div>
            <div class="content">
                <div class="section-title" style="border: none; padding: 0; margin-bottom: 20px;">Platform Wide Last 24 Hours Activity</div>
                <div class="metric-grid">
                    <div class="metric-card">
                        <div class="metric-label">Jobs Attempted</div>
                        <div class="metric-value">{metrics.get('total_jobs_attempted', 0)}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Jobs Submitted</div>
                        <div class="metric-value" style="color: #48BB78;">{metrics.get('total_jobs_submitted', 0)}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Total Events</div>
                        <div class="metric-value" style="color: #F6AD55;">{metrics.get('total_events', 0)}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Failed</div>
                        <div class="metric-value" style="color: #F56565;">{metrics.get('total_jobs_failed', 0)}</div>
                    </div>
                </div>
                
                <div class="section-title">User Leaderboard (Last 24h)</div>
                <table class="user-table">
                    <thead>
                        <tr>
                            <th>Candidate Email</th>
                            <th style="text-align: right;">Jobs Submitted</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(f"<tr><td>{u['email']}</td><td style='text-align: right; font-weight: bold; color: #48BB78;'>{u['submitted']}</td></tr>" for u in metrics.get('user_breakdown', [])) if metrics.get('user_breakdown') else "<tr><td colspan='2' style='text-align: center; color: #A0AEC0;'>No jobs submitted in the last 24 hours.</td></tr>"}
                    </tbody>
                </table>
            </div>
            <div class="footer">
                Generated by WboxCLI at {datetime.now().strftime('%Y-%m-%d %H:%M:%S PST')}
            </div>
        </div>
    </body>
    </html>
    """
    return html


def send_daily_report(session: Session, owner_email: str) -> None:
    """Gather metrics from backend, build email, and send to the owner."""
    from jobcli.storage.repositories import ConfigRepository
    import requests
    import os
    from dotenv import load_dotenv
    
    # Load from ~/.jobcli/.env if it exists
    dotenv_path = os.path.expanduser("~/.jobcli/.env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        
    # Also load from current directory .env
    load_dotenv()
    
    config = ConfigRepository(session).get_all()
    # Try to get from .env first, then config db, then fallback to localhost
    backend_url = os.getenv("BACKEND_URL") or getattr(config, "api_base_url", None) or getattr(config, "sync_server_url", None) or "http://localhost:8000"
    
    headers = {
        "X-Internal-Secret": "super-secret-weekly-workflow-key"
    }
    
    try:
        response = requests.get(
            f"{backend_url.rstrip('/')}/api/analytics/daily-summary".replace("/api/api/", "/api/"),
            headers=headers
        )
        response.raise_for_status()
        metrics = response.json()
    except Exception as e:
        print(f"Failed to fetch global metrics from backend: {e}")
        metrics = {
            "total_jobs_attempted": 0,
            "total_jobs_submitted": 0,
            "total_events": 0,
            "total_jobs_failed": 0,
            "user_breakdown": []
        }
    
    
    html_content = build_email_html(metrics)

    # Email configuration
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"WboxCLI Daily Analytics Report - {datetime.now().strftime('%Y-%m-%d')}"
    msg["From"] = smtp_user or "noreply@wboxcli.local"
    msg["To"] = owner_email

    part = MIMEText(html_content, "html")
    msg.attach(part)

    if smtp_user and smtp_pass:
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(msg["From"], [msg["To"]], msg.as_string())
                print(f"Daily report sent successfully to {owner_email}")
        except Exception as e:
            print(f"Failed to send email: {e}")
    else:
        print("SMTP_USER and SMTP_PASS environment variables are not set. "
              "Email was not sent. Preview of HTML generated:")
        print("--------------------------------------------------")
        print(html_content[:500] + "...(truncated)")
        print("--------------------------------------------------")
