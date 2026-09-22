from django.db import models
from django.contrib.auth.models import User


class Company(models.Model):

    USER_TYPES = [
        ('supplier', 'Supplier / Waste Generator'),
        ('buyer', 'Buyer / Recycler'),
        ('both', 'Dual Enterprise (Both Buyer & Supplier)'),
    ]

    STATUS = [
        ('pending', 'Pending Verification'),
        ('auto_verified', 'Auto Verified'),
        ('manual_approved', 'Manually Approved'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('flagged', 'Flagged for Review'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='company'
    )

    company_name = models.CharField(max_length=200)

    registration_number = models.CharField(
        max_length=100,
        unique=True
    )

    gstin = models.CharField(
        max_length=15,
        unique=True
    )

    authorized_person = models.CharField(
        max_length=150
    )

    phone = models.CharField(
        max_length=15
    )

    address = models.TextField()

    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPES
    )

    permit_document = models.FileField(
        upload_to='permits/',
        blank=True,
        null=True,
        help_text='Upload business registration certificate or pollution control permit.'
    )

    logo_image = models.FileField(
        upload_to='company_logos/',
        blank=True,
        null=True,
        help_text='Enterprise profile picture or company logo.'
    )

    verification_status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='pending'
    )

    # Email OTP Verification
    email_otp = models.CharField(
        max_length=6,
        blank=True,
        default="",
        help_text="6-digit Email verification OTP code"
    )
    is_email_verified = models.BooleanField(
        default=False,
        help_text="Whether company contact email is verified via OTP"
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    @property
    def is_verified(self):
        return self.verification_status in ['verified', 'auto_verified', 'manual_approved']

    @property
    def can_sell(self):
        return self.user_type in ['supplier', 'both']

    @property
    def can_buy(self):
        return self.user_type in ['buyer', 'both']

    def __str__(self):
        return f"{self.company_name} ({self.get_user_type_display()})"
