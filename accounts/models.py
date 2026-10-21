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

    # Email Registration OTP Lifecycle
    email_otp = models.CharField(
        max_length=6,
        blank=True,
        default="",
        help_text="6-digit Email verification OTP code"
    )
    otp_created_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when registration OTP was generated"
    )
    otp_attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of failed registration OTP attempts"
    )
    is_email_verified = models.BooleanField(
        default=False,
        help_text="Whether company contact email is verified via OTP"
    )

    # Password Reset OTP Lifecycle (Completely Separate from Registration OTP)
    reset_otp = models.CharField(
        max_length=6,
        blank=True,
        default="",
        help_text="6-digit Password Reset OTP code"
    )
    reset_otp_created_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when reset OTP was generated"
    )
    reset_otp_attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of failed reset OTP attempts"
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


class CompanyLocation(models.Model):
    LOCATION_TYPES = [
        ('godown', 'Storage Godown'),
        ('warehouse', 'Warehouse / Hub'),
        ('factory', 'Factory / Production Plant'),
        ('processing_unit', 'Processing Unit'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='locations'
    )
    location_name = models.CharField(
        max_length=200,
        help_text="Facility or godown identifier name (e.g. Aluva Main Godown)"
    )
    location_type = models.CharField(
        max_length=30,
        choices=LOCATION_TYPES,
        default='godown'
    )
    address = models.TextField(
        help_text="Detailed physical address"
    )
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text="Latitude coordinate (e.g. 10.0261)"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text="Longitude coordinate (e.g. 76.3125)"
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Designate this as the primary operating facility/godown"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_primary', 'location_name']
        verbose_name = 'Company Location'
        verbose_name_plural = 'Company Locations'

    def save(self, *args, **kwargs):
        # Transactional constraint: at most one primary location per company
        if self.is_primary and self.company_id:
            CompanyLocation.objects.filter(company=self.company, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        elif not self.is_primary and self.company_id:
            # If this is the only location for the company, make it primary automatically
            if not CompanyLocation.objects.filter(company=self.company).exclude(pk=self.pk).exists():
                self.is_primary = True
        super().save(*args, **kwargs)

    @property
    def has_coordinates(self):
        return self.latitude is not None and self.longitude is not None

    def __str__(self):
        role_label = self.get_location_type_display()
        primary_badge = " [Primary]" if self.is_primary else ""
        return f"{self.location_name} ({role_label}){primary_badge} — {self.company.company_name}"

