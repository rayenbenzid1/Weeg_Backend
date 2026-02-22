"""
test_email_smtp.py
Placez ce fichier à la racine du backend et exécutez :
    python test_email_smtp.py

Ce script teste la connexion SMTP directement, en dehors de Django,
pour isoler le problème de livraison.
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Config (identique à votre .env) ──────────────────────────────────────────
HOST     = "mail.digitalia.ly"
PORT     = 465
USER     = "weeg@digitalia.ly"
PASSWORD = "pfe2026@fasitunisie"
TO       = "weeg@digitalia.ly"          # ← changez si vous voulez tester un autre destinataire
# ─────────────────────────────────────────────────────────────────────────────

def test_smtp():
    print(f"\n{'='*60}")
    print(f"  Test SMTP — {HOST}:{PORT} (SSL)")
    print(f"{'='*60}\n")

    # 1. Résolution DNS
    import socket
    print(f"[1/4] Résolution DNS de {HOST}...")
    try:
        ip = socket.gethostbyname(HOST)
        print(f"      ✅ OK → {ip}")
    except socket.gaierror as e:
        print(f"      ❌ ÉCHEC DNS : {e}")
        print("      → Vérifiez que mail.digitalia.ly est accessible depuis ce réseau.")
        return

    # 2. Connexion TCP port 465
    print(f"\n[2/4] Connexion TCP à {HOST}:{PORT}...")
    try:
        sock = socket.create_connection((HOST, PORT), timeout=10)
        sock.close()
        print(f"      ✅ Port {PORT} ouvert")
    except Exception as e:
        print(f"      ❌ ÉCHEC connexion TCP : {e}")
        print("      → Le port 465 est peut-être bloqué par votre firewall / FAI.")
        return

    # 3. Login SMTP SSL
    print(f"\n[3/4] Authentification SMTP (USER: {USER})...")
    try:
        context = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(HOST, PORT, context=context, timeout=15)
        smtp.login(USER, PASSWORD)
        print(f"      ✅ Login réussi")
    except smtplib.SMTPAuthenticationError as e:
        print(f"      ❌ Authentification échouée : {e}")
        print("      → Vérifiez EMAIL_HOST_USER et EMAIL_HOST_PASSWORD dans .env")
        return
    except ssl.SSLError as e:
        print(f"      ❌ Erreur SSL : {e}")
        print("      → Essayez EMAIL_USE_SSL=False et EMAIL_PORT=587 avec TLS")
        return
    except Exception as e:
        print(f"      ❌ Erreur connexion : {e}")
        return

    # 4. Envoi d'un email de test
    print(f"\n[4/4] Envoi de l'email de test vers {TO}...")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "[FASI] ✅ Test SMTP — si vous lisez ceci, tout fonctionne"
        msg["From"]    = f"FASI <{USER}>"
        msg["To"]      = TO

        text = "Test SMTP FASI — l'email a bien été envoyé par Django."
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:40px auto;
                    padding:30px;border:1px solid #e2e8f0;border-radius:10px;">
            <h2 style="color:#4f46e5;">✅ Test SMTP réussi</h2>
            <p>Si vous lisez cet email, la configuration SMTP de FASI est correcte.</p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
            <p style="color:#94a3b8;font-size:12px;">
                Host : {HOST}:{PORT} | User : {USER}
            </p>
        </div>
        """

        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        smtp.sendmail(USER, [TO], msg.as_string())
        smtp.quit()
        print(f"      ✅ Email envoyé avec succès !")
        print(f"\n{'='*60}")
        print(f"  Vérifiez votre boîte {TO}")
        print(f"  (y compris Spam / Courrier indésirable / Autres)")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"      ❌ Échec envoi : {e}")
        smtp.quit()


if __name__ == "__main__":
    test_smtp()