"""
test_email_smtp.py
Place this file at the root of the backend and run:
    python test_email_smtp.py

This script tests the SMTP connection directly, outside of Django,
to isolate delivery issues.
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Configuration (same as your .env) ────────────────────────────────────────
HOST     = "mail.digitalia.ly"
PORT     = 465
USER     = "weeg@digitalia.ly"
PASSWORD = "pfe2026@fasitunisie"
TO       = "weeg@digitalia.ly"          # ← change this if you want to test another recipient
# ─────────────────────────────────────────────────────────────────────────────

def test_smtp():
    print(f"\n{'='*60}")
    print(f"  SMTP Test — {HOST}:{PORT} (SSL)")
    print(f"{'='*60}\n")

    # 1. DNS resolution
    import socket
    print(f"[1/4] Resolving DNS for {HOST}...")
    try:
        ip = socket.gethostbyname(HOST)
        print(f"      ✅ OK → {ip}")
    except socket.gaierror as e:
        print(f"      ❌ DNS FAILURE: {e}")
        print("      → Check that mail.digitalia.ly is reachable from this network.")
        return

    # 2. TCP connection to port 465
    print(f"\n[2/4] TCP connection to {HOST}:{PORT}...")
    try:
        sock = socket.create_connection((HOST, PORT), timeout=10)
        sock.close()
        print(f"      ✅ Port {PORT} is open")
    except Exception as e:
        print(f"      ❌ TCP connection FAILED: {e}")
        print("      → Port 465 might be blocked by your firewall / ISP.")
        return

    # 3. SMTP SSL login
    print(f"\n[3/4] SMTP authentication (USER: {USER})...")
    try:
        context = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(HOST, PORT, context=context, timeout=15)
        smtp.login(USER, PASSWORD)
        print(f"      ✅ Login successful")
    except smtplib.SMTPAuthenticationError as e:
        print(f"      ❌ Authentication failed: {e}")
        print("      → Check EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in .env")
        return
    except ssl.SSLError as e:
        print(f"      ❌ SSL error: {e}")
        print("      → Try EMAIL_USE_SSL=False and EMAIL_PORT=587 with TLS")
        return
    except Exception as e:
        print(f"      ❌ Connection error: {e}")
        return

    # 4. Sending test email
    print(f"\n[4/4] Sending test email to {TO}...")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "[WEEG] ✅ SMTP Test — if you read this, everything works"
        msg["From"]    = f"WEEG <{USER}>"
        msg["To"]      = TO

        text = "WEEG SMTP Test — this email was successfully sent via SMTP."
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:40px auto;
                    padding:30px;border:1px solid #e2e8f0;border-radius:10px;">
            <h2 style="color:#4f46e5;">✅ SMTP Test Successful</h2>
            <p>If you're reading this email, the WEEG SMTP configuration is correct.</p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
            <p style="color:#94a3b8;font-size:12px;">
                Host: {HOST}:{PORT} | User: {USER}
            </p>
        </div>
        """

        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        smtp.sendmail(USER, [TO], msg.as_string())
        smtp.quit()
        print(f"      ✅ Email sent successfully!")
        print(f"\n{'='*60}")
        print(f"  Please check your inbox at {TO}")
        print(f"  (including Spam / Junk / Other folders)")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"      ❌ Sending failed: {e}")
        smtp.quit()


if __name__ == "__main__":
    test_smtp()