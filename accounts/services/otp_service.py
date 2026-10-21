"""
Secure Email OTP Service for Registration & Password Reset.
Handles:
- Cryptographically secure 6-digit OTP generation
- Expiry tracking: 1 minute (60 seconds) for Password Reset, 10 minutes for Registration
- Resend cooldown enforcement (60 seconds)
- Attempt limiting (maximum 5 attempts before lockout)
- Single-use invalidation
- SMTP dispatch with clean error reporting
- Complete separation of registration OTPs and password reset OTPs
"""

import logging
import secrets
from datetime import timedelta
from typing import Tuple, Dict, Any, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth.models import User

from accounts.models import Company

logger = logging.getLogger(__name__)

REGISTRATION_OTP_EXPIRY_MINUTES = 10
RESET_OTP_EXPIRY_SECONDS = 60  # Exactly 1 minute as requested
OTP_MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


def generate_secure_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP code."""
    code = secrets.randbelow(900000) + 100000
    return str(code)


def get_registration_otp_remaining_seconds(company: Company) -> int:
    """Returns the seconds remaining before registration cooldown expires."""
    if not company or not company.otp_created_at:
        return 0
    elapsed = (timezone.now() - company.otp_created_at).total_seconds()
    remaining = RESEND_COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining))


def get_reset_otp_remaining_seconds(company: Company) -> int:
    """Returns the seconds remaining before the 1-minute reset OTP expires."""
    if not company or not company.reset_otp_created_at or not company.reset_otp:
        return 0
    elapsed = (timezone.now() - company.reset_otp_created_at).total_seconds()
    remaining = RESET_OTP_EXPIRY_SECONDS - elapsed
    return max(0, int(remaining))


def send_registration_otp(user: User, company: Company) -> Tuple[bool, str]:
    """
    Generates and dispatches a 6-digit registration verification OTP via SMTP.
    Returns (success: bool, error_message: str).
    """
    can_resend, wait_sec = can_resend_registration_otp(company)
    if not can_resend:
        return False, f"Please wait {wait_sec} seconds before requesting a new verification code."

    otp_code = generate_secure_otp()
    now = timezone.now()

    company.email_otp = otp_code
    company.otp_created_at = now
    company.otp_attempts = 0
    company.save(update_fields=['email_otp', 'otp_created_at', 'otp_attempts'])

    subject = "Your Verification OTP — Circular Waste Exchange"
    message = (
        f"Hello {user.username},\n\n"
        f"Thank you for registering your company '{company.company_name}' on the Circular Waste Exchange.\n\n"
        f"Your 6-digit email verification code is: {otp_code}\n\n"
        f"This code will expire in {REGISTRATION_OTP_EXPIRY_MINUTES} minutes.\n"
        f"If you did not initiate this registration, please ignore this email.\n\n"
        f"Best regards,\n"
        f"Kerala Circular Waste Intelligence Platform"
    )

    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@circularexchange.org'),
            recipient_list=[user.email],
            fail_silently=False,
        )
        if sent > 0:
            return True, ""
        return False, "SMTP server accepted request but reported 0 recipients delivered."
    except Exception as e:
        logger.error(f"Failed to send registration OTP email to {user.email}: {e}")
        return False, f"Email delivery failed: {str(e)}"


def can_resend_registration_otp(company: Company) -> Tuple[bool, int]:
    """Returns (can_resend: bool, wait_seconds: int)."""
    if not company.otp_created_at:
        return True, 0
    elapsed = (timezone.now() - company.otp_created_at).total_seconds()
    if elapsed < RESEND_COOLDOWN_SECONDS:
        return False, int(RESEND_COOLDOWN_SECONDS - elapsed)
    return True, 0


def verify_registration_otp(company: Company, entered_otp: str) -> Dict[str, Any]:
    """
    Validates entered OTP against company.email_otp.
    Enforces expiry (10 min) and max attempts (5).
    Clears OTP upon success or exhaustion.
    """
    entered = (entered_otp or "").strip()

    if not company.email_otp:
        return {
            "valid": False,
            "message": "No active verification code found. Please request a new OTP.",
            "expired": True,
            "attempts_left": 0,
        }

    # Check expiry
    if company.otp_created_at:
        age = timezone.now() - company.otp_created_at
        if age > timedelta(minutes=REGISTRATION_OTP_EXPIRY_MINUTES):
            company.email_otp = ""
            company.save(update_fields=['email_otp'])
            return {
                "valid": False,
                "message": "This verification code has expired. Please request a new OTP.",
                "expired": True,
                "attempts_left": 0,
            }

    # Check attempts limit
    if company.otp_attempts >= OTP_MAX_ATTEMPTS:
        company.email_otp = ""
        company.save(update_fields=['email_otp'])
        return {
            "valid": False,
            "message": "Maximum verification attempts exceeded. This code has been invalidated. Please request a new OTP.",
            "expired": True,
            "attempts_left": 0,
        }

    # Compare code
    if entered == company.email_otp:
        company.is_email_verified = True
        company.email_otp = ""
        company.verified_at = timezone.now()
        company.otp_attempts = 0
        company.save(update_fields=['is_email_verified', 'email_otp', 'verified_at', 'otp_attempts'])
        return {
            "valid": True,
            "message": "Email verified successfully!",
            "expired": False,
            "attempts_left": OTP_MAX_ATTEMPTS,
        }
    else:
        company.otp_attempts += 1
        attempts_left = max(0, OTP_MAX_ATTEMPTS - company.otp_attempts)
        if attempts_left == 0:
            company.email_otp = ""
            msg = "Incorrect OTP. Maximum attempts exceeded. Code invalidated. Please request a new code."
        else:
            msg = f"Invalid verification code. {attempts_left} attempt(s) remaining."
        company.save(update_fields=['otp_attempts', 'email_otp'])
        return {
            "valid": False,
            "message": msg,
            "expired": attempts_left == 0,
            "attempts_left": attempts_left,
        }


def send_password_reset_otp(user: User) -> Tuple[bool, str]:
    """
    Generates and dispatches a 6-digit password reset OTP via SMTP with 1-minute validity.
    Keeps password reset OTP completely separate from registration OTP.
    Returns (success: bool, error_message: str).
    """
    company = getattr(user, 'company', None)
    if company:
        can_resend, wait_sec = can_resend_password_reset_otp(company)
        if not can_resend:
            return False, f"Please wait {wait_sec} seconds before requesting a new password reset code."

    otp_code = generate_secure_otp()
    now = timezone.now()

    if company:
        company.reset_otp = otp_code
        company.reset_otp_created_at = now
        company.reset_otp_attempts = 0
        company.save(update_fields=['reset_otp', 'reset_otp_created_at', 'reset_otp_attempts'])

    subject = "Password Reset Verification Code — Circular Waste Exchange"
    message = (
        f"Hello {user.username},\n\n"
        f"A request was received to reset your password on the Circular Waste Intelligence Platform.\n\n"
        f"Your 6-digit password reset verification code is: {otp_code}\n\n"
        f"This code will expire in 1 minute (60 seconds).\n"
        f"If you did not request a password reset, please ignore this email; your account remains secure.\n\n"
        f"Security Team,\n"
        f"Circular Waste Intelligence Platform"
    )

    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'security@circularexchange.org'),
            recipient_list=[user.email],
            fail_silently=False,
        )
        if sent > 0:
            return True, ""
        return False, "SMTP server accepted request but reported 0 recipients delivered."
    except Exception as e:
        logger.error(f"Failed to send password reset OTP email to {user.email}: {e}")
        return False, f"Email delivery failed: {str(e)}"


def can_resend_password_reset_otp(company: Company) -> Tuple[bool, int]:
    """Returns (can_resend: bool, wait_seconds: int) for password reset."""
    if not company.reset_otp_created_at:
        return True, 0
    elapsed = (timezone.now() - company.reset_otp_created_at).total_seconds()
    if elapsed < RESEND_COOLDOWN_SECONDS:
        return False, int(RESEND_COOLDOWN_SECONDS - elapsed)
    return True, 0


def verify_password_reset_otp(user: User, entered_otp: str) -> Dict[str, Any]:
    """
    Validates entered OTP against company.reset_otp.
    Enforces expiry (1 minute / 60 seconds) and max attempts (5).
    Clears reset OTP upon successful single-use or lockout.
    """
    company = getattr(user, 'company', None)
    entered = (entered_otp or "").strip()

    if not company or not company.reset_otp:
        return {
            "valid": False,
            "message": "No active password reset request found. Please request a new code.",
            "expired": True,
            "attempts_left": 0,
        }

    # Check expiry (1 minute / 60 seconds)
    if company.reset_otp_created_at:
        age = timezone.now() - company.reset_otp_created_at
        if age > timedelta(seconds=RESET_OTP_EXPIRY_SECONDS):
            company.reset_otp = ""
            company.save(update_fields=['reset_otp'])
            return {
                "valid": False,
                "message": "This password reset code has expired after 1 minute. Please request a new code.",
                "expired": True,
                "attempts_left": 0,
            }

    # Check attempts
    if company.reset_otp_attempts >= OTP_MAX_ATTEMPTS:
        company.reset_otp = ""
        company.save(update_fields=['reset_otp'])
        return {
            "valid": False,
            "message": "Maximum verification attempts exceeded. This reset code has been invalidated. Please request a new code.",
            "expired": True,
            "attempts_left": 0,
        }

    # Verify code
    if entered == company.reset_otp:
        # Valid single-use code: clear code immediately
        company.reset_otp = ""
        company.reset_otp_attempts = 0
        company.save(update_fields=['reset_otp', 'reset_otp_attempts'])
        return {
            "valid": True,
            "message": "Reset code verified successfully.",
            "expired": False,
            "attempts_left": OTP_MAX_ATTEMPTS,
        }
    else:
        company.reset_otp_attempts += 1
        attempts_left = max(0, OTP_MAX_ATTEMPTS - company.reset_otp_attempts)
        if attempts_left == 0:
            company.reset_otp = ""
            msg = "Incorrect OTP. Maximum attempts exceeded. Code invalidated. Please request a new code."
        else:
            msg = f"Invalid reset code. {attempts_left} attempt(s) remaining."
        company.save(update_fields=['reset_otp_attempts', 'reset_otp'])
        return {
            "valid": False,
            "message": msg,
            "expired": attempts_left == 0,
            "attempts_left": attempts_left,
        }
