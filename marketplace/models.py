from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date
from accounts.models import Company


class MaterialCategory(models.Model):
    """
    Standard category reference with admin-managed standard price per ton
    and carbon offset factor (kg CO₂e per ton).
    """
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=30, unique=True)
    standard_price_per_ton = models.DecimalField(max_digits=10, decimal_places=2, default=20000.00)
    carbon_offset_factor = models.DecimalField(max_digits=8, decimal_places=2, default=1.65, help_text="kg CO₂e avoided per kg/ton of byproduct reused")
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Material Categories"

    def __str__(self):
        return f"{self.name} (Std Rate: ₹{self.standard_price_per_ton}/t)"


class MaterialListing(models.Model):
    """
    Waste stream byproduct listings offered by suppliers.
    """
    CATEGORY_CHOICES = [
        ("rubber", "Scrap Rubber"),
        ("textile", "Textile Remnants"),
        ("coconut", "Coconut Shells"),
        ("plastic", "Plastic Fragments"),
        ("fish", "Fish Scales"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("pending_permit", "Pending Permit"),
        ("fulfilled", "Fulfilled"),
    ]

    APPROVAL_STATUS_CHOICES = [
        ("pending", "Pending Admin Review"),
        ("approved", "Approved & Live on Marketplace"),
        ("rejected", "Rejected"),
    ]

    supplier = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="listings")
    category_ref = models.ForeignKey(MaterialCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="listings")
    material_name = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="rubber")
    batch_id = models.CharField(max_length=50, blank=True, default="")
    description = models.TextField(blank=True, default="", help_text="Detailed material composition, source process, and usage recommendations")
    price_per_ton = models.DecimalField(max_digits=10, decimal_places=2)
    recommended_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    volume_tons = models.DecimalField(max_digits=10, decimal_places=2, help_text="Total available quantity")
    quantity_unit = models.CharField(max_length=20, default="Tons", choices=[("Tons", "Tons"), ("Kg", "Kilograms"), ("Litres", "Litres")])
    condition = models.CharField(max_length=50, default="Recyclable Clean", choices=[("Recyclable Clean", "Recyclable Clean"), ("Unsorted Bulk", "Unsorted Bulk"), ("Reconditioned", "Reconditioned"), ("Processed Scrap", "Processed Scrap")])
    purity_percent = models.PositiveSmallIntegerField(default=90)
    trust_score = models.PositiveSmallIntegerField(default=85)
    location = models.CharField(max_length=255, default="Kochi, Kerala")
    permit_verified = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default="approved")
    mismatch_warning = models.CharField(max_length=255, blank=True, default="", help_text="Consistency checking alert if category conflicts with name/image")
    is_active = models.BooleanField(default=True)

    # Waste Stream Image & Quality Assurance Protocol
    image = models.FileField(upload_to="listings/", blank=True, null=True, help_text="Upload waste stream batch photo (JPG, PNG, WebP)")
    quality_certificate = models.FileField(upload_to="quality_certs/", blank=True, null=True, help_text="Chemical lab test report & purity certificate")
    quality_grade = models.CharField(
        max_length=20,
        choices=[
            ("grade_a", "Grade A - Certified Lab Tested"),
            ("grade_b", "Grade B - Secondary Feedstock"),
            ("grade_c", "Grade C - Raw Unsorted Byproduct"),
        ],
        default="grade_a"
    )
    sampling_protocol = models.CharField(
        max_length=255,
        default="Standard Composite Sampling per ASTM D6323 with pre-dispatch retention sample held"
    )
    lab_accreditation_number = models.CharField(
        max_length=100,
        blank=True,
        default="NABL-KL-2026/TC-8812",
        help_text="Accredited testing laboratory certification reference ID"
    )
    lab_audit_status = models.CharField(
        max_length=25,
        choices=[
            ("audited_verified", "Audited & Lab Verified"),
            ("pending_audit", "Pending Lab Audit"),
            ("self_declared", "Supplier Self-Declared"),
        ],
        default="audited_verified"
    )

    # Technical Specifications
    moq_tons = models.DecimalField(max_digits=8, decimal_places=2, default=10.00, help_text="Minimum Order Quantity (tons)")
    lead_time_days = models.PositiveIntegerField(default=4)
    packaging_type = models.CharField(max_length=150, default="Woven poly bulk bags, 500 kg")
    moisture_percent = models.DecimalField(max_digits=5, decimal_places=2, default=1.80)
    contamination_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.40)
    particle_size = models.CharField(max_length=100, default="2–5 mm")
    compliance_id = models.CharField(max_length=100, default="KPCB-WM-22910")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.batch_id:
            prefix = self.category[:2].upper() if self.category else "BT"
            import random
            self.batch_id = f"{prefix}-{random.randint(2000, 9999)}"
        super().save(*args, **kwargs)

    @property
    def estimated_carbon_savings(self):
        factor = 1.65
        if self.category_ref:
            factor = float(self.category_ref.carbon_offset_factor)
        elif self.category == "rubber":
            factor = 1.69
        elif self.category == "textile":
            factor = 2.10
        elif self.category == "coconut":
            factor = 1.45
        elif self.category == "plastic":
            factor = 1.85
        elif self.category == "fish":
            factor = 1.15
        return round(float(self.volume_tons) * factor, 1)

    def __str__(self):
        return f"{self.material_name} [{self.batch_id}] — {self.supplier.company_name}"


class Certificate(models.Model):
    """
    Supplier environmental permits, lab chemical test sheets, and ISO certificates.
    """
    STATUS_CHOICES = [
        ("pending", "Pending Verification"),
        ("verified", "Verified"),
        ("expired", "Expired"),
        ("rejected", "Rejected"),
    ]

    supplier = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="certificates")
    certificate_name = models.CharField(max_length=255)
    certificate_type = models.CharField(max_length=100, default="Environmental Permit")
    material = models.CharField(max_length=150, default="Industrial Scrap")
    issue_date = models.DateField(default=date.today)
    expiry_date = models.DateField()
    document = models.FileField(upload_to="certificates/", blank=True, null=True)
    verification_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="verified")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_expired(self):
        if self.expiry_date and self.expiry_date < date.today():
            return True
        return False

    def check_and_update_expiry(self):
        if self.is_expired and self.verification_status != "expired":
            self.verification_status = "expired"
            self.save(update_fields=["verification_status"])

    def __str__(self):
        return f"{self.certificate_name} — {self.supplier.company_name}"


class ProcurementRequest(models.Model):
    """
    Buyer procurement requirement and orders sent to suppliers with Amazon/Flipkart-style live tracking.
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("partially_fulfilled", "Partially Fulfilled"),
        ("fulfilled", "Fulfilled"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    DELIVERY_STATUS_CHOICES = [
        ("order_confirmed", "Order Confirmed & Escrow Reserved"),
        ("quality_inspected", "Factory Weighbridge & Quality Inspected"),
        ("in_transit", "In Transit Along Highway Corridor"),
        ("delivered", "Delivered & Weighment Verified"),
    ]

    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="requests")
    buyer_company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name="procurement_orders")
    listing = models.ForeignKey(MaterialListing, on_delete=models.CASCADE, related_name="requests")
    volume_requested = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True, default="")
    
    # Flipkart / Amazon style live logistics tracking
    tracking_number = models.CharField(max_length=40, blank=True, default="")
    delivery_status = models.CharField(max_length=30, choices=DELIVERY_STATUS_CHOICES, default="in_transit")
    vehicle_number = models.CharField(max_length=50, default="KL-07-BW-4921 (20t Closed Container Truck)")
    driver_contact = models.CharField(max_length=50, default="+91 98460 22100 (Kerala Freight Carriers)")
    current_location = models.CharField(max_length=255, default="NH 544 Aluva Bypass, En route to Palakkad")
    eta_hours = models.CharField(max_length=50, default="3.5 Hours")
    tracking_progress_percent = models.PositiveIntegerField(default=65)

    # Transportation corridor
    origin_facility = models.CharField(max_length=255, blank=True, default="Kochi Industrial Belt, Kerala")
    destination_facility = models.CharField(max_length=255, blank=True, default="Palakkad Manufacturing Complex, Kerala")
    transport_mode = models.CharField(max_length=100, default="Closed Container Bulk Carrier (20t)")
    estimated_distance_km = models.PositiveIntegerField(default=142)
    checkpoint_toll = models.DecimalField(max_digits=8, decimal_places=2, default=450.00, help_text="Paliakkara/Highway Corridor Toll & Border Clearance")
    payment_status = models.CharField(
        max_length=30,
        choices=[
            ('escrow_held', 'Buyer Escrow Held (Pending Supplier Approval)'),
            ('released_to_supplier', 'Released to Supplier (Dispatched)'),
            ('refunded', 'Refunded to Buyer'),
        ],
        default='escrow_held'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.tracking_number:
            import random
            self.tracking_number = f"AG-KL-{random.randint(10000, 99999)}"
        super().save(*args, **kwargs)

    def subtotal(self):
        return round(self.volume_requested * self.listing.price_per_ton, 2)

    def estimated_freight(self):
        # Base dispatch ₹1500 + Highway/Checkpoint Toll ₹450 + (volume * distance * ₹3.20/t-km)
        base = 1500.00
        toll = float(self.checkpoint_toll)
        distance_component = float(self.volume_requested) * self.estimated_distance_km * 3.20
        return round(base + toll + distance_component, 2)

    def total_cost(self):
        return round(float(self.subtotal()) + self.estimated_freight(), 2)

    def __str__(self):
        return f"{self.buyer.username} → {self.listing.material_name} ({self.volume_requested}t) [{self.status}]"


class AggregationPool(models.Model):
    """
    Combines small byproduct volumes from multiple suppliers to fulfill
    a single buyer target requirement (e.g. 500 tons order).
    """
    STATUS_CHOICES = [
        ("filling", "Filling"),
        ("fulfilled", "Fulfilled"),
        ("cancelled", "Cancelled"),
    ]

    title = models.CharField(max_length=255)
    material_name = models.CharField(max_length=200, default="Shredded Tyre Crumb Rubber")
    buyer_name = models.CharField(max_length=200, default="Kochi Infrastructure & Industrial Corp.")
    target_volume_tons = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    collected_volume_tons = models.DecimalField(max_digits=10, decimal_places=2, default=360.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="filling")
    contributing_suppliers_count = models.PositiveIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def progress_percent(self):
        if self.target_volume_tons <= 0:
            return 0
        pct = int((self.collected_volume_tons / self.target_volume_tons) * 100)
        return min(100, pct)

    @property
    def remaining_tons(self):
        return max(0, float(self.target_volume_tons) - float(self.collected_volume_tons))

    def __str__(self):
        return f"{self.title} ({self.collected_volume_tons}/{self.target_volume_tons}t)"


class ListingImage(models.Model):
    """
    Multiple angle photos for material stream listings (similar to Amazon / Flipkart).
    """
    listing = models.ForeignKey(MaterialListing, on_delete=models.CASCADE, related_name="gallery_images")
    image = models.FileField(upload_to="listing_gallery/", help_text="Additional angle photo")
    caption = models.CharField(max_length=150, blank=True, default="Angle View")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.listing.material_name} ({self.caption})"


class ReportedListing(models.Model):
    """
    Allows buyers or visitors to report fake, misleading, or impure listings to Admin.
    """
    listing = models.ForeignKey(MaterialListing, on_delete=models.CASCADE, related_name="reports")
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.CharField(max_length=255, help_text="Reason for reporting (e.g. Misleading image, Wrong category, Impure sample)")
    details = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"Report on {self.listing.material_name}: {self.reason}"


class FundingProject(models.Model):
    """
    Circular economy project funding module UI.
    """
    STATUS_CHOICES = [
        ("active", "Active Funding"),
        ("funded", "Fully Funded"),
        ("closed", "Closed"),
    ]
    title = models.CharField(max_length=255)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="funding_projects")
    category = models.CharField(max_length=100, default="Circular Recycling Infrastructure")
    description = models.TextField()
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, default=500000.00)
    raised_amount = models.DecimalField(max_digits=12, decimal_places=2, default=120000.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def progress_percent(self):
        if self.target_amount > 0:
            return min(int((self.raised_amount / self.target_amount) * 100), 100)
        return 0

    def __str__(self):
        return f"{self.title} (₹{self.raised_amount} / ₹{self.target_amount})"
