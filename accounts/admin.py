from django.contrib import admin
from django.utils import timezone
from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):

    list_display = (
        'company_name',
        'registration_number',
        'gstin',
        'user_type',
        'is_email_verified',
        'verification_status',
        'has_permit',
        'created_at',
    )

    list_filter = (
        'is_email_verified',
        'verification_status',
        'user_type',
        'created_at',
    )

    search_fields = (
        'company_name',
        'gstin',
        'registration_number',
        'authorized_person',
    )

    readonly_fields = (
        'created_at',
        'verified_at',
    )

    actions = [
        'approve_companies',
        'flag_companies',
        'reject_companies',
    ]

    @admin.display(boolean=True, description='Permit Uploaded')
    def has_permit(self, obj):
        return bool(obj.permit_document)

    @admin.action(description='Approve selected companies (Manual)')
    def approve_companies(self, request, queryset):
        queryset.update(
            verification_status='manual_approved',
            verified_at=timezone.now()
        )

    @admin.action(description='Flag selected companies for review')
    def flag_companies(self, request, queryset):
        queryset.update(
            verification_status='flagged'
        )

    @admin.action(description='Reject selected companies')
    def reject_companies(self, request, queryset):
        queryset.update(
            verification_status='rejected'
        )
