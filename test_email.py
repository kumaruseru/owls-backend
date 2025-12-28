
import os
import django
from django.conf import settings
from django.core.mail import send_mail

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

def test_email():
    print(f"Testing email configuration...")
    print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
    print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
    print(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
    print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
    
    recipient = settings.EMAIL_HOST_USER  # Send to self
    print(f"Sending test email to: {recipient}")
    
    try:
        send_mail(
            subject="Test Email from OWLS",
            message="This is a test email to verify SMTP configuration.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        print("SUCCESS: Email sent successfully!")
    except Exception as e:
        print(f"FAILURE: Failed to send email.")
        print(f"Error: {e}")

if __name__ == "__main__":
    test_email()
