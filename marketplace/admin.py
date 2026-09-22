from django.contrib import admin
from .models import (
    MaterialCategory,
    MaterialListing,
    ListingImage,
    ReportedListing,
    FundingProject,
    Certificate,
    ProcurementRequest,
    AggregationPool,
)


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 1
    fields = ('image', 'caption', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'standard_price_per_ton', 'carbon_offset_factor', 'updated_at')
    search_fields = ('name', 'code')


from django.utils.html import format_html


@admin.register(MaterialListing)
class MaterialListingAdmin(admin.ModelAdmin):
    list_display = (
        'image_thumbnail',
        'material_name',
        'batch_id',
        'category',
        'image_detected_category',
        'verification_badge',
        'use_category_symbol',
        'approval_status',
        'supplier',
        'volume_tons',
        'price_per_ton',
        'is_active',
        'created_at',
    )
    list_filter = (
        'approval_status',
        'image_verification_status',
        'use_category_symbol',
        'category',
        'status',
        'is_active',
        'permit_verified',
    )
    search_fields = ('material_name', 'batch_id', 'supplier__company_name', 'location', 'image_detected_category')
    readonly_fields = (
        'image_preview_large',
        'verification_badge',
        'use_category_symbol',
        'image_verification_status',
        'image_verification_score',
        'image_detected_category',
        'created_at',
        'updated_at',
    )
    inlines = [ListingImageInline]
    actions = ['approve_listings', 'reject_listings', 'manual_review_listings']

    def image_thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 44px; height: 44px; object-fit: cover; border-radius: 6px; border: 1px solid #e2e8f0;" />',
                obj.image.url
            )
        return format_html('<span style="color: #94a3b8; font-size: 11px;">No photo</span>')
    image_thumbnail.short_description = "Image"

    def image_preview_large(self, obj):
        if obj.image:
            return format_html(
                '<div style="margin-bottom: 8px;"><img src="{}" style="max-width: 280px; max-height: 220px; object-fit: cover; border-radius: 8px; border: 1px solid #cbd5e1; box-shadow: 0 1px 3px rgba(0,0,0,0.1);" /></div>',
                obj.image.url
            )
        return "No image uploaded"
    image_preview_large.short_description = "Uploaded Waste Stream Photo"

    def verification_badge(self, obj):
        badge_colors = {
            "Likely Match": "#10b981",       # emerald green
            "Manual Review": "#f59e0b",      # amber orange
            "Possible Mismatch": "#ef4444",  # rose red
        }
        color = badge_colors.get(obj.image_verification_status, "#64748b")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 11px; white-space: nowrap; display: inline-block;">'
            '{} ({:.0f}%)</span>',
            color,
            obj.image_verification_status or "Pending",
            obj.image_verification_score or 0.0
        )
    verification_badge.short_description = "Verification Status"

    @admin.action(description="Approve selected waste stream listings")
    def approve_listings(self, request, queryset):
        rows = queryset.update(approval_status='approved')
        self.message_user(request, f"{rows} listing(s) approved and published to the marketplace.")

    @admin.action(description="Reject selected waste stream listings")
    def reject_listings(self, request, queryset):
        rows = queryset.update(approval_status='rejected')
        self.message_user(request, f"{rows} listing(s) rejected.")

    @admin.action(description="Flag selected listings for Manual Review")
    def manual_review_listings(self, request, queryset):
        rows = queryset.update(approval_status='pending', image_verification_status='Manual Review')
        self.message_user(request, f"{rows} listing(s) marked for manual review.")


@admin.register(ListingImage)
class ListingImageAdmin(admin.ModelAdmin):
    list_display = ('listing', 'caption', 'uploaded_at')
    search_fields = ('listing__material_name', 'caption')


@admin.register(ReportedListing)
class ReportedListingAdmin(admin.ModelAdmin):
    list_display = ('listing', 'reported_by', 'reason', 'is_resolved', 'created_at')
    list_filter = ('is_resolved', 'created_at')
    search_fields = ('listing__material_name', 'reported_by__username', 'details')
    actions = ['mark_resolved']

    @admin.action(description="Mark selected reports as resolved")
    def mark_resolved(self, request, queryset):
        queryset.update(is_resolved=True)
        self.message_user(request, "Selected report(s) marked as resolved.")


@admin.register(FundingProject)
class FundingProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'category', 'target_amount', 'raised_amount', 'progress_percent', 'status', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('title', 'company__company_name', 'description')


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_name', 'supplier', 'certificate_type', 'material', 'expiry_date', 'verification_status')
    list_filter = ('verification_status', 'certificate_type')
    search_fields = ('certificate_name', 'supplier__company_name', 'material')


@admin.register(ProcurementRequest)
class ProcurementRequestAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'listing', 'volume_requested', 'estimated_distance_km', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('buyer__username', 'listing__material_name', 'origin_facility', 'destination_facility')


@admin.register(AggregationPool)
class AggregationPoolAdmin(admin.ModelAdmin):
    list_display = ('title', 'material_name', 'buyer_name', 'target_volume_tons', 'collected_volume_tons', 'status')
    list_filter = ('status',)
    search_fields = ('title', 'buyer_name', 'material_name')

