from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Q, Count
from datetime import date
from decimal import Decimal

from .models import (
    MaterialListing,
    ListingImage,
    ReportedListing,
    FundingProject,
    ProcurementRequest,
    MaterialCategory,
    Certificate,
    AggregationPool,
)
from .forms import (
    MaterialListingForm,
    CertificateForm,
    StandardRateConfigForm,
    ReportedListingForm,
    FundingPledgeForm,
)
from .services.pricing import calculate_recommended_rate, get_standard_rate
from .services.matching import calculate_match_score
from .services.carbon import calculate_carbon_savings
from .services.aggregation import BatchCartService
from .services.logistics import calculate_corridor_distance
from .services.extractor import extract_certificate_data
from accounts.models import Company
from accounts.decorators import supplier_required, buyer_required


def index(request):
    """
    Marketplace Home: dynamic material catalog, search query, category ribbon,
    filter sidebar, and industrial symbiosis matches.
    Only approved, active listings are publicly visible.
    """
    listings = MaterialListing.objects.filter(is_active=True, approval_status='approved').select_related('supplier')

    # Keyword Search
    q = request.GET.get('q', '').strip()
    if q:
        listings = listings.filter(
            Q(material_name__icontains=q) |
            Q(location__icontains=q) |
            Q(supplier__company_name__icontains=q) |
            Q(batch_id__icontains=q)
        )

    # Category Filter
    category = request.GET.get('category')
    if category and category != 'all':
        listings = listings.filter(category=category)

    # Minimum Volume Filter
    min_volume = request.GET.get('min_volume')
    if min_volume and min_volume.isdigit():
        listings = listings.filter(volume_tons__gte=float(min_volume))

    # Purity Filter
    min_purity = request.GET.get('min_purity')
    if min_purity and min_purity.isdigit():
        listings = listings.filter(purity_percent__gte=int(min_purity))

    # Verification Filter
    verified_only = request.GET.get('verified_only')
    if verified_only:
        listings = listings.filter(permit_verified=True)

    # Quality Grade Filter (Grade A, Grade B, Grade C)
    quality_grade = request.GET.get('quality_grade')
    if quality_grade and quality_grade != 'all':
        listings = listings.filter(quality_grade=quality_grade)

    # Annotate listings with match score and carbon savings for presentation
    target_cat = category if (category and category != 'all') else None
    for item in listings:
        match_info = calculate_match_score(
            item,
            target_category=target_cat,
            min_purity=int(min_purity) if min_purity and min_purity.isdigit() else 85
        )
        item.match_score = match_info['score_percent']
        item.match_label = match_info['label']

    # Platform impact statistics
    total_diverted = listings.aggregate(total=Sum('volume_tons'))['total'] or 14200
    estimated_credits = int(float(total_diverted) * 0.24) if total_diverted else 3400

    context = {
        'listings': listings,
        'total_listings_count': listings.count(),
        'total_diverted': int(total_diverted),
        'estimated_credits': estimated_credits,
        'current_category': category,
        'current_quality_grade': quality_grade or 'all',
        'min_volume': min_volume or '0',
        'min_purity': min_purity or '70',
        'q': q,
    }
    return render(request, 'index.html', context)


def product_detail(request, pk):
    """
    Detailed byproduct stream view: specifications, chemical testing,
    supplier trust score, MOQ volume calculation, gallery images, and reporting.
    """
    listing = get_object_or_404(MaterialListing, pk=pk, is_active=True)
    carbon_info = calculate_carbon_savings(listing.volume_tons, listing.category)
    match_info = calculate_match_score(listing, target_category=listing.category)

    # Related listings from same category that are approved
    related_listings = MaterialListing.objects.filter(
        category=listing.category,
        is_active=True,
        approval_status='approved'
    ).exclude(pk=listing.pk)[:3]

    gallery_images = listing.gallery_images.all()
    report_form = ReportedListingForm()

    context = {
        'listing': listing,
        'carbon_info': carbon_info,
        'match_info': match_info,
        'related_listings': related_listings,
        'gallery_images': gallery_images,
        'report_form': report_form,
    }
    return render(request, 'product.html', context)


@login_required
@supplier_required
def dashboard(request):
    """
    Supplier B2B Dashboard:
    - Metrics: Volume listed, requests count, reliability %, carbon reduction
    - Listed waste streams table with Edit/Delete/Apply Recommended Rate
    - Supply aggregation pools with CSS progress bars
    - Incoming procurement requests with Accept/Reject
    - Certificate vault
    """
    # Verify company profile exists
    company = getattr(request.user, 'company', None)
    if not company:
        messages.error(request, "Company profile not found for this user.")
        return redirect('login')

    listings = MaterialListing.objects.filter(supplier=company).order_by('-created_at')
    incoming_requests = ProcurementRequest.objects.filter(listing__supplier=company).select_related('buyer', 'listing').order_by('-created_at')
    certificates = Certificate.objects.filter(supplier=company).order_by('-created_at')
    
    # Auto update certificate expiry
    for cert in certificates:
        cert.check_and_update_expiry()

    # Aggregation pools for this supplier's primary materials
    pools = AggregationPool.objects.all().order_by('-created_at')[:4]

    # Calculate Top Metric Cards
    total_listed_volume = listings.aggregate(total=Sum('volume_tons'))['total'] or Decimal('0.00')
    requests_count = incoming_requests.count()
    
    # Calculate carbon reduction
    total_co2e = sum([float(item.volume_tons) * 1.69 for item in listings])

    context = {
        'company': company,
        'listings': listings,
        'incoming_requests': incoming_requests,
        'certificates': certificates,
        'pools': pools,
        'metric_volume': f"{total_listed_volume:.0f} t",
        'metric_requests': requests_count,
        'metric_reliability': "98%",
        'metric_carbon': f"{total_co2e:.0f} t",
    }
    return render(request, 'dashboard.html', context)


@login_required
@supplier_required
def listing_create(request):
    """Supplier or Dual Enterprise creates a new waste stream listing with live recommended price calculation."""
    company = getattr(request.user, 'company', None)
    if not company or not company.can_sell:
        messages.error(request, "Only verified suppliers or dual-role enterprises can create material listings.")
        return redirect('index')

    if request.method == 'POST':
        form = MaterialListingForm(request.POST, request.FILES)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.supplier = company
            listing.approval_status = 'pending'
            
            # Automatically calculate and store recommended rate
            rec_rate = calculate_recommended_rate(
                listing.category,
                listing.purity_percent,
                float(listing.volume_tons)
            )
            listing.recommended_price = rec_rate
            
            # If price per ton is not specified or 0, default to recommended
            if not listing.price_per_ton or listing.price_per_ton <= 0:
                listing.price_per_ton = rec_rate

            listing.save()

            # Process multiple gallery images (Amazon/Flipkart thumbnail style)
            additional_images = request.FILES.getlist('additional_images')
            for idx, img_file in enumerate(additional_images):
                ListingImage.objects.create(
                    listing=listing,
                    image=img_file,
                    caption=f"Angle {idx + 1}"
                )

            messages.success(
                request,
                f"Waste stream '{listing.material_name}' submitted for admin review (Batch ID {listing.batch_id})! "
                f"It will be publicly visible once approved by administrators."
            )
            return redirect('dashboard')
    else:
        # Prepopulate with standard recommended values for Kerala industrial zone
        form = MaterialListingForm(initial={
            'category': 'rubber',
            'volume_tons': 100.0,
            'purity_percent': 90,
            'price_per_ton': 18000.00,
            'location': company.address or 'Kochi Industrial Corridor, Kerala',
        })

    # Recommended price preview for initial form
    std_rate = get_standard_rate('rubber')
    rec_preview = calculate_recommended_rate('rubber', 90, 100.0)

    return render(request, 'listing_form.html', {
        'form': form,
        'is_edit': False,
        'standard_rate': std_rate,
        'recommended_price': rec_preview,
    })


@login_required
@supplier_required
def listing_edit(request, pk):
    """Supplier edits an existing listing."""
    company = getattr(request.user, 'company', None)
    listing = get_object_or_404(MaterialListing, pk=pk, supplier=company)

    if request.method == 'POST':
        form = MaterialListingForm(request.POST, request.FILES, instance=listing)
        if form.is_valid():
            updated_listing = form.save(commit=False)
            # Recompute recommended price
            rec_rate = calculate_recommended_rate(
                updated_listing.category,
                updated_listing.purity_percent,
                float(updated_listing.volume_tons)
            )
            updated_listing.recommended_price = rec_rate
            updated_listing.save()

            # Handle any new additional images
            additional_images = request.FILES.getlist('additional_images')
            for idx, img_file in enumerate(additional_images):
                ListingImage.objects.create(
                    listing=updated_listing,
                    image=img_file,
                    caption=f"Additional view {idx + 1}"
                )

            messages.success(request, f"Listing '{updated_listing.material_name}' updated successfully.")
            return redirect('dashboard')
    else:
        form = MaterialListingForm(instance=listing)

    rec_preview = calculate_recommended_rate(listing.category, listing.purity_percent, float(listing.volume_tons))
    return render(request, 'listing_form.html', {
        'form': form,
        'is_edit': True,
        'listing': listing,
        'standard_rate': get_standard_rate(listing.category),
        'recommended_price': rec_preview,
    })


@login_required
@supplier_required
def listing_delete(request, pk):
    """Supplier removes a listing."""
    company = getattr(request.user, 'company', None)
    listing = get_object_or_404(MaterialListing, pk=pk, supplier=company)
    name = listing.material_name
    listing.delete()
    messages.success(request, f"Waste stream '{name}' has been deleted.")
    return redirect('dashboard')


@login_required
@supplier_required
def apply_recommended_price(request, pk):
    """Applies the recommended rate directly to the listing."""
    company = getattr(request.user, 'company', None)
    listing = get_object_or_404(MaterialListing, pk=pk, supplier=company)
    
    rec_rate = calculate_recommended_rate(listing.category, listing.purity_percent, float(listing.volume_tons))
    listing.price_per_ton = rec_rate
    listing.recommended_price = rec_rate
    listing.save(update_fields=['price_per_ton', 'recommended_price'])
    
    messages.success(request, f"Applied recommended rate ₹{rec_rate}/ton to '{listing.material_name}'.")
    return redirect('dashboard')


def calculate_price_api(request):
    """Live AJAX API for instant price recommendations on listing form."""
    category = request.GET.get('category', 'rubber')
    purity = int(request.GET.get('purity', 90))
    volume = float(request.GET.get('volume', 100))

    std_rate = get_standard_rate(category)
    rec_rate = calculate_recommended_rate(category, purity, volume)

    return JsonResponse({
        'category': category,
        'standard_rate': float(std_rate),
        'recommended_rate': float(rec_rate),
        'formula': f"₹{std_rate} × ({purity}%) × volume factor"
    })


@login_required
@supplier_required
def request_respond(request, pk):
    """Supplier accepts or rejects an incoming buyer procurement request."""
    company = getattr(request.user, 'company', None)
    proc_request = get_object_or_404(ProcurementRequest, pk=pk, listing__supplier=company)

    action = request.POST.get('action') or request.GET.get('action')
    if action == 'accept':
        proc_request.status = 'accepted'
        proc_request.payment_status = 'released_to_supplier'
        proc_request.delivery_status = 'in_transit'
        proc_request.tracking_progress_percent = 70

        # Reduce available waste stream volume upon purchase
        listing = proc_request.listing
        listing.volume_tons = max(Decimal('0.00'), listing.volume_tons - proc_request.volume_requested)
        if listing.volume_tons <= Decimal('0.00'):
            listing.status = 'fulfilled'
            listing.is_active = False
        listing.save(update_fields=['volume_tons', 'status', 'is_active'])

        messages.success(
            request,
            f"Procurement order from {proc_request.buyer.username} for {proc_request.volume_requested}t ACCEPTED. "
            f"Escrow payment released to supplier account & delivery corridor tracking plan activated."
        )
    elif action == 'reject':
        proc_request.status = 'rejected'
        proc_request.payment_status = 'refunded'
        messages.warning(
            request,
            f"Procurement request from {proc_request.buyer.username} REJECTED. Held escrow refunded back to buyer."
        )
    
    proc_request.save(update_fields=['status', 'payment_status', 'delivery_status', 'tracking_progress_percent'])
    return redirect('dashboard')


@login_required
@supplier_required
def certificate_upload(request):
    """Supplier uploads a certificate to vault."""
    company = getattr(request.user, 'company', None)
    if not company:
        return redirect('login')

    if request.method == 'POST':
        form = CertificateForm(request.POST, request.FILES)
        if form.is_valid():
            cert = form.save(commit=False)
            cert.supplier = company
            cert.save()
            messages.success(request, f"Certificate '{cert.certificate_name}' uploaded to vault.")
            return redirect('dashboard')
    else:
        form = CertificateForm()

    return render(request, 'certificate_form.html', {'form': form})


# ============================================================
# BATCH CART & MULTI-SUPPLIER AGGREGATION
# ============================================================

@login_required
@buyer_required
def cart_view(request):
    """
    Batch Cart Page:
    Displays aggregated tonnage from multiple suppliers, target progress bar,
    freight route mapping placeholder, and breakdown summary.
    """
    cart_service = BatchCartService(request.session)

    if request.method == 'POST' and 'update_target' in request.POST:
        target_tons = request.POST.get('target_volume_tons', 500)
        target_material = request.POST.get('target_material', 'Scrap Rubber')
        cart_service.set_target(float(target_tons), target_material)
        messages.success(request, f"Target requirement updated to {target_tons} tons.")
        return redirect('cart_view')

    summary = cart_service.get_summary()
    return render(request, 'checkout.html', {'summary': summary})


@login_required
@buyer_required
def cart_add(request, pk):
    """Adds a listing to the multi-supplier batch cart."""
    listing = get_object_or_404(MaterialListing, pk=pk, is_active=True)
    volume = request.POST.get('volume_requested') or request.GET.get('volume') or listing.moq_tons

    cart_service = BatchCartService(request.session)
    cart_service.add_listing(listing, float(volume))
    messages.success(request, f"Added {volume}t of '{listing.material_name}' to your Batch Cart.")
    return redirect('cart_view')


@login_required
@buyer_required
def cart_remove(request, pk):
    """Removes a listing from the batch cart."""
    cart_service = BatchCartService(request.session)
    cart_service.remove_listing(pk)
    messages.info(request, "Material stream removed from Batch Cart.")
    return redirect('cart_view')


@login_required
@buyer_required
def cart_checkout(request):
    """Converts batch cart into procurement orders for each contributing supplier."""
    cart_service = BatchCartService(request.session)
    summary = cart_service.get_summary()

    if not summary['items']:
        messages.error(request, "Your Batch Cart is empty.")
        return redirect('index')

    buyer_company = getattr(request.user, 'company', None)
    created_count = 0
    dest_facility = buyer_company.address if (buyer_company and buyer_company.address) else "Palakkad Industrial Corridor, Kerala"
    
    for item in summary['items']:
        listing = get_object_or_404(MaterialListing, pk=item['listing_id'])
        dist_km = calculate_corridor_distance(listing.location, dest_facility)
        ProcurementRequest.objects.create(
            buyer=request.user,
            buyer_company=buyer_company,
            listing=listing,
            volume_requested=Decimal(str(item['volume_tons'])),
            status='pending',
            payment_status='escrow_held',
            delivery_status='order_confirmed',
            tracking_progress_percent=25,
            origin_facility=f"{listing.supplier.company_name}, {listing.location}",
            destination_facility=dest_facility,
            transport_mode="Closed Container Bulk Carrier (20t)",
            estimated_distance_km=dist_km,
            current_location="Awaiting Supplier Dispatch Confirmation",
        )
        created_count += 1

    # Record Aggregation Pool record
    AggregationPool.objects.create(
        title=f"{summary['target_material']} Batch Order — {request.user.username}",
        material_name=summary['target_material'],
        buyer_name=buyer_company.company_name if buyer_company else request.user.username,
        target_volume_tons=summary['target_tons'],
        collected_volume_tons=summary['collected_tons'],
        contributing_suppliers_count=len(summary['items']),
        status='fulfilled' if summary['is_fully_filled'] else 'filling'
    )

    cart_service.clear()
    messages.success(
        request,
        f"Procurement request executed! Successfully transmitted orders to {created_count} suppliers across Kerala corridor. "
        f"Payment is held securely in escrow pending supplier dispatch approval."
    )
    return redirect('buyer_orders')


@login_required
@buyer_required
def checkout(request, pk):
    """Direct single-listing procurement checkout."""
    listing = get_object_or_404(MaterialListing, pk=pk)

    if request.method == "POST":
        volume = request.POST.get("volume_requested", listing.moq_tons)
        buyer_company = getattr(request.user, 'company', None)
        dest_facility = buyer_company.address if (buyer_company and buyer_company.address) else "Kochi Logistics Park, Kerala"
        dist_km = calculate_corridor_distance(listing.location, dest_facility)
        
        ProcurementRequest.objects.create(
            buyer=request.user,
            buyer_company=buyer_company,
            listing=listing,
            volume_requested=Decimal(str(volume)),
            status="pending",
            payment_status="escrow_held",
            delivery_status="order_confirmed",
            tracking_progress_percent=25,
            origin_facility=f"{listing.supplier.company_name}, {listing.location}",
            destination_facility=dest_facility,
            transport_mode="Closed Container Bulk Carrier (20t)",
            estimated_distance_km=dist_km,
            current_location="Awaiting Supplier Dispatch Confirmation",
        )
        messages.success(
            request,
            f"Procurement request for {volume} tons submitted to {listing.supplier.company_name}. "
            f"Funds transferred and held securely in escrow pending supplier dispatch approval."
        )
        return redirect("buyer_orders")

    return render(request, "checkout.html", {
        "listing": listing,
        "single_mode": True,
    })


@login_required
@buyer_required
def buyer_orders(request):
    """Buyer's order tracking & procurement status view."""
    requests = ProcurementRequest.objects.filter(buyer=request.user).select_related('listing', 'listing__supplier').order_by('-created_at')
    return render(request, 'buyer_orders.html', {'orders': requests})


# ============================================================
# REPORTING & CERTIFICATE SUGGESTION APIS
# ============================================================

@login_required
def report_listing(request, pk):
    """Buyers/users report suspicious, mismatched, or counterfeit material listings to Admin."""
    listing = get_object_or_404(MaterialListing, pk=pk)
    if request.method == 'POST':
        form = ReportedListingForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.listing = listing
            report.reported_by = request.user
            report.save()
            messages.success(
                request,
                f"Thank you. Your report regarding '{listing.material_name}' has been lodged with Platform Admin for verification."
            )
            return redirect('product_detail', pk=pk)
    else:
        form = ReportedListingForm()

    return render(request, 'report_listing.html', {'form': form, 'listing': listing})


def extract_certificate_api(request):
    """
    Simulated AI/NLP Certificate Parsing Endpoint:
    Accepts an uploaded certificate file and returns structured suggested values
    (purity, grade, volume, lab accreditation) to auto-fill the listing form.
    """
    if request.method == 'POST' and request.FILES.get('certificate'):
        file_obj = request.FILES['certificate']
        extracted_data = extract_certificate_data(file_obj, file_obj.name)
        return JsonResponse({
            'status': 'success',
            'data': extracted_data,
            'message': 'Certificate analyzed successfully.'
        })
    return JsonResponse({'status': 'error', 'message': 'No certificate file uploaded.'}, status=400)


# ============================================================
# CIRCULAR FUNDING & INNOVATION GRANTS
# ============================================================

def funding_list(request):
    """Displays active circular innovation and recycling projects seeking community funding."""
    projects = FundingProject.objects.all().order_by('-created_at')
    pledge_form = FundingPledgeForm()
    return render(request, 'funding.html', {
        'projects': projects,
        'pledge_form': pledge_form,
    })


@login_required
def funding_pledge(request, pk):
    """Allows authenticated users/companies to pledge financial backing to a circular project."""
    project = get_object_or_404(FundingProject, pk=pk)
    if request.method == 'POST':
        amount = request.POST.get('amount') or request.POST.get('pledge_amount') or 5000
        try:
            val = Decimal(str(amount))
            project.raised_amount += val
            if project.raised_amount >= project.target_amount:
                project.status = "funded"
            project.save(update_fields=['raised_amount', 'status'])
            messages.success(
                request,
                f"Thank you! You successfully pledged ₹{val:,.2f} towards '{project.title}'."
            )
        except Exception:
            messages.error(request, "Invalid pledge amount entered.")
    return redirect('funding_list')



# ============================================================
# CUSTOM ADMIN DASHBOARD
# ============================================================

@staff_member_required
def custom_admin_dashboard(request):
    """
    Custom Admin Dashboard:
    - Total registered companies, pending verification, verified companies
    - Active waste listings, pending approval listings, reported listings
    - Standard price configuration table with update capability
    - Active aggregation pools
    """
    if request.method == 'POST' and 'update_rate' in request.POST:
        cat_id = request.POST.get('category_id')
        new_rate = request.POST.get('standard_price_per_ton')
        new_offset = request.POST.get('carbon_offset_factor')
        cat = get_object_or_404(MaterialCategory, pk=cat_id)
        if new_rate:
            cat.standard_price_per_ton = Decimal(new_rate)
        if new_offset:
            cat.carbon_offset_factor = Decimal(new_offset)
        cat.save()
        messages.success(request, f"Standard price for {cat.name} updated to ₹{cat.standard_price_per_ton}/ton.")
        return redirect('custom_admin_dashboard')

    if request.method == 'POST' and 'review_listing' in request.POST:
        listing_id = request.POST.get('listing_id')
        l_action = request.POST.get('listing_action')
        target_listing = get_object_or_404(MaterialListing, pk=listing_id)
        if l_action == 'approve':
            target_listing.approval_status = 'approved'
            messages.success(request, f"Listing '{target_listing.material_name}' has been APPROVED and published to the marketplace.")
        elif l_action == 'reject':
            target_listing.approval_status = 'rejected'
            messages.warning(request, f"Listing '{target_listing.material_name}' has been REJECTED.")
        target_listing.save(update_fields=['approval_status'])
        return redirect('custom_admin_dashboard')

    categories = MaterialCategory.objects.all().order_by('name')
    companies = Company.objects.all().order_by('-created_at')
    listings = MaterialListing.objects.all().order_by('-created_at')
    proc_requests = ProcurementRequest.objects.all().order_by('-created_at')
    pools = AggregationPool.objects.all().order_by('-created_at')

    pending_listings = listings.filter(approval_status='pending')
    reported_listings = ReportedListing.objects.filter(is_resolved=False).order_by('-created_at')

    total_companies = companies.count()
    pending_companies = companies.filter(verification_status__in=['pending', 'flagged']).count()
    verified_companies = companies.filter(verification_status__in=['auto_verified', 'manual_approved', 'verified']).count()
    active_listings = listings.filter(is_active=True, approval_status='approved').count()
    total_volume = listings.filter(approval_status='approved').aggregate(total=Sum('volume_tons'))['total'] or Decimal('0.00')
    total_co2e_saved = sum([float(l.volume_tons) * 1.69 for l in listings.filter(approval_status='approved')])

    context = {
        'total_companies': total_companies,
        'pending_companies': pending_companies,
        'verified_companies': verified_companies,
        'active_listings': active_listings,
        'pending_listings': pending_listings,
        'pending_listings_count': pending_listings.count(),
        'reported_listings': reported_listings,
        'reported_listings_count': reported_listings.count(),
        'total_volume': f"{total_volume:.0f} t",
        'total_co2e': f"{total_co2e_saved:.0f} t",
        'procurement_requests_count': proc_requests.count(),
        'categories': categories,
        'pools': pools,
        'recent_companies': companies[:6],
        'recent_listings': listings[:8],
    }
    return render(request, 'admin_dashboard.html', context)


@staff_member_required
def verification_panel(request):
    """Admin Company Verification Hub: review permits, approve, reject, flag companies."""
    if request.method == "POST":
        company_id = request.POST.get("company_id")
        action = request.POST.get("action")
        company = get_object_or_404(Company, pk=company_id)

        if action == "approve":
            company.verification_status = "manual_approved"
            company.verified_at = timezone.now()
            action_desc = "MANUALLY APPROVED"
        elif action == "flag":
            company.verification_status = "flagged"
            action_desc = "FLAGGED FOR REVIEW"
        elif action == "reject":
            company.verification_status = "rejected"
            action_desc = "REJECTED"
        else:
            company.verification_status = "pending"
            action_desc = "RESET TO PENDING"

        company.save()
        messages.success(request, f"Company '{company.company_name}' was {action_desc}.")
        return redirect("verification_panel")

    pending_companies = Company.objects.filter(verification_status__in=["pending", "flagged"]).order_by("-created_at")
    verified_companies = Company.objects.filter(verification_status__in=["auto_verified", "manual_approved", "verified"]).order_by("-created_at")
    rejected_companies = Company.objects.filter(verification_status="rejected").order_by("-created_at")

    context = {
        "pending_companies": pending_companies,
        "verified_companies": verified_companies,
        "rejected_companies": rejected_companies,
        "total_companies": Company.objects.count(),
        "count_pending": pending_companies.count(),
        "count_verified": verified_companies.count(),
        "count_rejected": rejected_companies.count(),
    }
    return render(request, "admin.html", context)
