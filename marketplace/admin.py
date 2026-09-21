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


@admin.register(MaterialListing)
class MaterialListingAdmin(admin.ModelAdmin):
    list_display = (
        'material_name',
        'batch_id',
        'category',
        'supplier',
        'volume_tons',
        'quantity_unit',
        'price_per_ton',
        'recommended_price',
        'purity_percent',
        'approval_status',
        'mismatch_warning',
        'is_active',
        'created_at',
    )
    list_filter = ('approval_status', 'category', 'status', 'is_active', 'permit_verified')
    search_fields = ('material_name', 'batch_id', 'supplier__company_name', 'location')
    inlines = [ListingImageInline]
    actions = ['approve_listings', 'reject_listings']

    @admin.action(description="Approve selected waste stream listings")
    def approve_listings(self, request, queryset):
        rows = queryset.update(approval_status='approved')
        self.message_user(request, f"{rows} listing(s) approved and published to the marketplace.")

    @admin.action(description="Reject selected waste stream listings")
    def reject_listings(self, request, queryset):
        rows = queryset.update(approval_status='rejected')
        self.message_user(request, f"{rows} listing(s) rejected.")


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

