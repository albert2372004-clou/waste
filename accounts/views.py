import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction

from .models import Company, CompanyLocation
from .forms import (
    CompanySignupForm,
    CompanyLocationForm,
    ForgotPasswordForm,
    VerifyResetOTPForm,
    SetNewPasswordForm,
    ResetPasswordOTPForm,
    EnterpriseProfileForm,
)
from .services.otp_service import (
    send_registration_otp,
    verify_registration_otp,
    can_resend_registration_otp,
    get_registration_otp_remaining_seconds,
    send_password_reset_otp,
    verify_password_reset_otp,
    can_resend_password_reset_otp,
    get_reset_otp_remaining_seconds,
)

logger = logging.getLogger(__name__)


def signup(request):
    """
    Step 1 of Registration: Enterprise enters company and account information.
    Upon validation, User & Company are created with is_email_verified=False.
    A secure 6-digit OTP is sent through SMTP, and user is redirected to verify_otp.
    """
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == 'POST':
        form = CompanySignupForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=form.cleaned_data['username'],
                        email=form.cleaned_data['email'],
                        password=form.cleaned_data['password']
                    )

                    company = Company.objects.create(
                        user=user,
                        company_name=form.cleaned_data['company_name'],
                        registration_number=form.cleaned_data['registration_number'],
                        gstin=form.cleaned_data['gstin'],
                        authorized_person=form.cleaned_data['authorized_person'],
                        phone=form.cleaned_data['phone'],
                        address=form.cleaned_data['address'],
                        user_type=form.cleaned_data['user_type'],
                        permit_document=form.cleaned_data.get('permit_document'),
                        is_email_verified=False,
                        verification_status='pending'
                    )

                    # Parse and save multiple godowns / warehouses submitted during registration
                    loc_names = request.POST.getlist('loc_name[]') or request.POST.getlist('loc_name')
                    loc_types = request.POST.getlist('loc_type[]') or request.POST.getlist('loc_type')
                    loc_addresses = request.POST.getlist('loc_address[]') or request.POST.getlist('loc_address')
                    loc_lats = request.POST.getlist('loc_lat[]') or request.POST.getlist('loc_lat')
                    loc_lngs = request.POST.getlist('loc_lng[]') or request.POST.getlist('loc_lng')
                    loc_primary_val = request.POST.get('loc_primary', '0')

                    created_locations = 0
                    for i in range(len(loc_names)):
                        name = (loc_names[i] if i < len(loc_names) else '').strip()
                        addr = (loc_addresses[i] if i < len(loc_addresses) else '').strip()
                        ltype = (loc_types[i] if i < len(loc_types) else '').strip()
                        if not ltype:
                            ltype = 'warehouse' if company.can_sell else 'godown'

                        raw_lat = loc_lats[i] if i < len(loc_lats) else None
                        raw_lng = loc_lngs[i] if i < len(loc_lngs) else None
                        lat, lng = None, None
                        try:
                            if raw_lat not in [None, '', '—']:
                                lat = Decimal(str(raw_lat))
                            if raw_lng not in [None, '', '—']:
                                lng = Decimal(str(raw_lng))
                        except Exception:
                            pass

                        if name or addr or lat is not None:
                            is_primary = (str(i) == str(loc_primary_val)) or (created_locations == 0)
                            CompanyLocation.objects.create(
                                company=company,
                                location_name=name or (f"{company.company_name} - Warehouse {created_locations+1}" if company.can_sell else f"{company.company_name} - Godown {created_locations+1}"),
                                location_type=ltype,
                                address=addr or company.address,
                                latitude=lat,
                                longitude=lng,
                                is_primary=is_primary
                            )
                            created_locations += 1

                    # For suppliers/dual enterprises: if no warehouse location was explicitly provided,
                    # automatically generate a primary warehouse from their registered operating address.
                    if company.can_sell and created_locations == 0:
                        CompanyLocation.objects.create(
                            company=company,
                            location_name=f"{company.company_name} - Main Facility",
                            location_type='warehouse',
                            address=company.address,
                            latitude=None,
                            longitude=None,
                            is_primary=True
                        )

                # Store pending user ID in session for OTP verification
                request.session['pending_verification_user_id'] = user.id

                # Send 6-digit OTP via real SMTP
                success, err_msg = send_registration_otp(user, company)
                if success:
                    messages.success(
                        request,
                        f"Registration initiated! A 6-digit verification OTP has been sent to {user.email}. "
                        f"Please enter the code below to complete registration."
                    )
                else:
                    messages.warning(
                        request,
                        f"Registration details recorded, but the verification email could not be delivered: {err_msg}. "
                        f"Please verify your email address or click Resend OTP."
                    )

                return redirect('verify_otp')

            except Exception as e:
                logger.error(f"Signup error: {e}")
                messages.error(
                    request,
                    f'Registration failed. Please check your entries: {str(e)}'
                )
    else:
        form = CompanySignupForm()

    return render(request, 'accounts/register.html', {'form': form})


def verify_otp(request):
    """
    Step 2 of Registration: Enforces email OTP verification before completing registration.
    Checks expiry, attempt limits, and single-use invalidation.
    Workflow: Registration -> Email OTP Verification -> Registration Completion -> Login -> Admin Company Approval.
    """
    user_id = request.session.get('pending_verification_user_id')
    user = None
    if user_id:
        user = User.objects.filter(id=user_id).first()

    if not user:
        if request.user.is_authenticated:
            user = request.user

    if not user or not hasattr(user, 'company'):
        messages.error(request, "No pending registration found to verify. Please register or sign in.")
        return redirect('login')

    company = user.company
    can_resend, wait_sec = can_resend_registration_otp(company)
    remaining_sec = get_registration_otp_remaining_seconds(company)
    resend_wait_sec = wait_sec if not can_resend else 0

    if request.method == 'POST':
        entered_otp = (request.POST.get('otp') or request.POST.get('otp_code') or '').strip()
        result = verify_registration_otp(company, entered_otp)

        if result['valid']:
            # Clear pending session variable
            request.session.pop('pending_verification_user_id', None)
            
            # Email verification complete: redirect to login per required workflow
            messages.success(
                request,
                "✅ Email successfully verified with OTP! Registration is complete. "
                "Please sign in with your credentials. Your company account is now PENDING administrator review."
            )
            return redirect('login')
        else:
            messages.error(request, result['message'])

    return render(request, 'accounts/verify_otp.html', {
        'pending_user': user,
        'remaining_seconds': remaining_sec,
        'can_resend': can_resend,
        'wait_seconds': wait_sec,
        'resend_wait_seconds': resend_wait_sec,
    })


def resend_otp(request):
    """Resends registration verification OTP subject to 60-second cooldown."""
    user_id = request.session.get('pending_verification_user_id')
    user = User.objects.filter(id=user_id).first() if user_id else None

    if not user and request.user.is_authenticated:
        user = request.user

    if not user or not hasattr(user, 'company'):
        messages.error(request, "No pending registration found. Please sign in or register.")
        return redirect('login')

    company = user.company
    can_resend, wait_sec = can_resend_registration_otp(company)

    if not can_resend:
        messages.warning(request, f"Please wait {wait_sec} seconds before requesting a new verification code.")
        return redirect('verify_otp')

    success, err_msg = send_registration_otp(user, company)
    if success:
        messages.success(request, f"A fresh 6-digit verification OTP has been sent to {user.email}.")
    else:
        messages.error(request, f"Could not deliver verification email: {err_msg}")

    return redirect('verify_otp')


def switch_mode(request, mode):
    """Allows Dual-Role ('both') enterprises to switch between Buyer and Supplier modes."""
    if not request.user.is_authenticated:
        return redirect('login')

    company = getattr(request.user, 'company', None)
    if not company or company.user_type != 'both':
        messages.error(request, "Only Dual-Role enterprises can switch operation modes.")
        return redirect('index')

    if mode in ['buyer', 'supplier']:
        request.session['active_mode'] = mode
        messages.info(request, f"Switched to {mode.capitalize()} Mode.")
        if mode == 'supplier':
            return redirect('dashboard')
    return redirect('index')


def user_login(request):
    """
    User login with strict verification restrictions:
    1. Unverified email accounts cannot log in and are redirected to verify_otp.
    2. Company accounts must be approved by admin before marketplace access.
    """
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.is_staff:
            return redirect('verification_panel')
        if hasattr(request.user, 'company') and request.user.company.user_type == 'supplier':
            return redirect('dashboard')
        return redirect('index')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is None:
            messages.error(
                request,
                'Invalid username or password.'
            )
            return redirect('login')

        # Superusers and administrators
        if user.is_superuser or user.is_staff:
            login(request, user)
            return redirect('verification_panel')

        try:
            company = Company.objects.get(user=user)
        except Company.DoesNotExist:
            messages.error(
                request,
                'This account is not associated with a registered company.'
            )
            return redirect('login')

        # Enforcement: Prevent unverified users from logging in or bypassing verification
        if not company.is_email_verified:
            request.session['pending_verification_user_id'] = user.id
            messages.warning(
                request,
                'Your email address has not been verified yet. Please enter the verification OTP sent to your email.'
            )
            return redirect('verify_otp')

        if company.verification_status == 'rejected':
            messages.error(
                request,
                'Your company registration was rejected by the platform administrator.'
            )
            return redirect('login')

        if company.verification_status == 'flagged':
            messages.warning(
                request,
                'Your company documentation has been flagged for manual verification.'
            )
            return redirect('login')

        if company.verification_status == 'pending':
            messages.warning(
                request,
                'Your company account is currently pending verification. Marketplace access will activate once approved.'
            )
            return redirect('login')

        # Company is verified (verified, auto_verified, manual_approved)
        login(request, user)
        messages.success(request, f'Welcome back, {company.company_name}!')

        if company.user_type == 'supplier':
            return redirect('dashboard')
        else:
            return redirect('index')

    return render(
        request,
        'accounts/login.html'
    )


def user_logout(request):
    logout(request)
    return redirect('login')


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')

    if request.user.is_superuser:
        return redirect('/admin/')

    try:
        company = Company.objects.get(user=request.user)
    except Company.DoesNotExist:
        logout(request)
        messages.error(request, 'Company account information not found.')
        return redirect('login')

    return render(
        request,
        'accounts/dashboard.html',
        {'company': company}
    )


def forgot_password(request):
    """
    Step 1 of Password Reset:
    Generates 6-digit reset OTP and sends to registered email (valid for 1 minute).
    Uses generic responses to avoid revealing whether an email is registered.
    """
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            ident = form.cleaned_data['identifier'].strip()
            user = (
                User.objects.filter(username__iexact=ident).first()
                or User.objects.filter(email__iexact=ident).first()
            )

            if user and user.email:
                company = getattr(user, 'company', None)
                can_resend, wait_sec = can_resend_password_reset_otp(company) if company else (True, 0)

                request.session['reset_user_id'] = user.id
                request.session['reset_otp_verified'] = False
                parts = user.email.split('@')
                user_part = parts[0]
                domain_part = parts[1] if len(parts) > 1 else ''
                if len(user_part) > 2:
                    masked = f"{user_part[0]}***{user_part[-1]}@{domain_part}"
                else:
                    masked = f"***@{domain_part}"
                request.session['reset_email_masked'] = masked

                if not can_resend:
                    messages.info(
                        request,
                        f"A verification code was already dispatched recently to {masked}. "
                        f"You can request a new code in {wait_sec} seconds, or enter your active code below."
                    )
                    return redirect('reset_password_otp')

                success, err_msg = send_password_reset_otp(user)
                if not success:
                    logger.error(f"Failed to dispatch reset OTP to {user.email}: {err_msg}")
                    messages.error(request, f"Could not deliver email: {err_msg}")
            else:
                # Store sentinel to prevent user enumeration
                request.session['reset_user_id'] = -1
                request.session['reset_otp_verified'] = False
                request.session['reset_email_masked'] = 'your registered address'

            # Generic response to avoid user/email enumeration attacks
            messages.info(
                request,
                "If an account matching that username or email exists in our system, "
                "a 6-digit password reset code has been sent. It is valid for 1 minute."
            )
            return redirect('reset_password_otp')
    else:
        form = ForgotPasswordForm()

    return render(request, 'accounts/forgot_password.html', {'form': form})


def reset_password_otp(request):
    """
    Step 2 of Password Reset:
    Displays ONLY the OTP entry field with a decreasing 1-minute countdown timer.
    After 1 minute, the OTP becomes invalid.
    If valid, redirects to the Set New Password page ('set_new_password').
    """
    user_id = request.session.get('reset_user_id')
    if not user_id:
        messages.warning(request, "Please enter your username or email to request a password reset.")
        return redirect('forgot_password')

    if user_id == -1:
        # Dummy flow for unregistered identifier: prevent account enumeration
        if request.method == 'POST':
            messages.error(request, "Invalid or expired reset code. Please request a new code.")
            return render(request, 'accounts/reset_password_otp.html', {
                'form': VerifyResetOTPForm(request.POST),
                'user_email': 'your registered address',
                'remaining_seconds': 0,
                'can_resend': True,
                'wait_seconds': 0,
                'resend_wait_seconds': 0,
            })
        return render(request, 'accounts/reset_password_otp.html', {
            'form': VerifyResetOTPForm(),
            'user_email': 'your registered address',
            'remaining_seconds': 60,
            'can_resend': True,
            'wait_seconds': 0,
            'resend_wait_seconds': 0,
        })

    user = User.objects.filter(id=user_id).first()
    if not user:
        request.session.pop('reset_user_id', None)
        return redirect('forgot_password')

    company = getattr(user, 'company', None)
    can_resend, wait_sec = can_resend_password_reset_otp(company) if company else (True, 0)
    remaining_sec = get_reset_otp_remaining_seconds(company) if company else 0
    resend_wait_sec = wait_sec if not can_resend else 0

    if request.method == 'POST':
        form = VerifyResetOTPForm(request.POST)
        if form.is_valid():
            entered_otp = form.cleaned_data['otp'].strip()
            res = verify_password_reset_otp(user, entered_otp)

            if res['valid']:
                request.session['reset_otp_verified'] = True
                messages.success(request, "OTP verified successfully! Now set your new password.")
                return redirect('set_new_password')
            else:
                messages.error(request, res['message'])
    else:
        form = VerifyResetOTPForm()

    masked_email = request.session.get('reset_email_masked', 'your registered email')

    return render(request, 'accounts/reset_password_otp.html', {
        'form': form,
        'user_email': masked_email,
        'remaining_seconds': remaining_sec,
        'can_resend': can_resend,
        'wait_seconds': wait_sec,
        'resend_wait_seconds': resend_wait_sec,
    })


def set_new_password(request):
    """
    Step 3 of Password Reset:
    Displays New Password and Confirm Password options ONLY after OTP is verified.
    Saves new hashed password, preserves company verification status, and returns to Login page.
    """
    user_id = request.session.get('reset_user_id')
    otp_verified = request.session.get('reset_otp_verified')

    if not user_id or not otp_verified or user_id == -1:
        messages.warning(request, "Please verify your OTP code before setting a new password.")
        return redirect('forgot_password')

    user = User.objects.filter(id=user_id).first()
    if not user:
        request.session.pop('reset_user_id', None)
        request.session.pop('reset_otp_verified', None)
        return redirect('forgot_password')

    if request.method == 'POST':
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            new_pw = form.cleaned_data['new_password']
            user.set_password(new_pw)
            user.save()

            # Clean up session
            request.session.pop('reset_user_id', None)
            request.session.pop('reset_otp_verified', None)
            request.session.pop('reset_email_masked', None)

            messages.success(
                request,
                "Password updated successfully! Please log in with your new credentials."
            )
            return redirect('login')
    else:
        form = SetNewPasswordForm()

    return render(request, 'accounts/set_new_password.html', {'form': form})


def resend_reset_otp(request):
    """Resends password reset OTP subject to 60-second cooldown."""
    user_id = request.session.get('reset_user_id')
    if not user_id:
        messages.warning(request, "Session expired. Please request a new password reset.")
        return redirect('forgot_password')

    request.session['reset_otp_verified'] = False

    if user_id == -1:
        messages.success(request, "A new 6-digit password reset code has been sent to your email.")
        return redirect('reset_password_otp')

    user = User.objects.filter(id=user_id).first()
    if not user:
        messages.warning(request, "Session expired. Please request a new password reset.")
        return redirect('forgot_password')

    company = getattr(user, 'company', None)
    if company:
        can_resend, wait_sec = can_resend_password_reset_otp(company)
        if not can_resend:
            messages.warning(request, f"Please wait {wait_sec} seconds before requesting a new code.")
            return redirect('reset_password_otp')

    success, err_msg = send_password_reset_otp(user)
    if success:
        messages.success(request, "A new 6-digit password reset code has been sent to your email (valid for 1 minute).")
    else:
        messages.error(request, f"Could not deliver email: {err_msg}")

    return redirect('reset_password_otp')


@login_required
def profile_view(request):
    """
    Enterprise Profile Dashboard (Amazon/Flipkart Pro style):
    - Company Identity, Logo upload & editing
    - Role details (Buyer, Supplier, Both)
    - Full transaction & order history with tracking
    - Circular funding pledges & active benefit tiers
    - Safe Account Deactivation option preserving audit trails
    """
    from marketplace.models import ProcurementRequest, MaterialListing, ProjectPledge

    company = getattr(request.user, 'company', None)

    if request.method == 'POST':
        if 'deactivate_account' in request.POST:
            request.user.is_active = False
            request.user.save(update_fields=['is_active'])
            if company:
                company.verification_status = 'rejected'
                company.save(update_fields=['verification_status'])
            logout(request)
            messages.warning(
                request,
                "Your enterprise account has been deactivated. Historical transactions and compliance records remain archived for audit compliance."
            )
            return redirect('login')

        if 'update_profile' in request.POST:
            if company:
                form = EnterpriseProfileForm(request.POST, request.FILES, instance=company)
                if form.is_valid():
                    form.save()
                    new_email = form.cleaned_data.get('email')
                    if new_email and new_email != request.user.email:
                        request.user.email = new_email
                        request.user.save(update_fields=['email'])
                    messages.success(request, "Enterprise profile & corporate identity updated successfully!")
                    return redirect('profile')
            else:
                messages.error(request, "Only registered corporate enterprises can update profile details.")
                return redirect('profile')

    form = EnterpriseProfileForm(instance=company, initial={'email': request.user.email}) if company else None

    orders = ProcurementRequest.objects.filter(buyer=request.user).select_related('listing', 'listing__supplier').order_by('-created_at')
    listings = MaterialListing.objects.filter(supplier=company).order_by('-created_at') if company else []
    incoming_orders = ProcurementRequest.objects.filter(listing__supplier=company).select_related('buyer', 'listing').order_by('-created_at') if company else []
    pledges = ProjectPledge.objects.filter(contributor=request.user).select_related('project').order_by('-created_at')

    # Aggregations & Metrics
    total_spent = sum([float(o.volume_requested) * float(o.listing.price_per_ton) + float(o.checkpoint_toll) for o in orders if o.listing])
    total_volume_bought = sum([float(o.volume_requested) for o in orders])
    total_volume_sold = sum([float(l.volume_tons) for l in listings])
    total_pledged = sum([float(p.amount) for p in pledges])

    context = {
        'company': company,
        'form': form,
        'orders': orders,
        'listings': listings,
        'incoming_orders': incoming_orders,
        'pledges': pledges,
        'locations': company.locations.all() if company else [],
        'total_spent': total_spent,
        'total_volume_bought': total_volume_bought,
        'total_volume_sold': total_volume_sold,
        'total_pledged': total_pledged,
    }
    return render(request, 'accounts/profile.html', context)


# ======================================================================
# MULTIPLE GODOWN & WAREHOUSE MANAGEMENT WITH OPENSTREETMAP LEAFLET
# ======================================================================

@login_required
def location_list(request):
    """Lists all registered facilities, warehouses, and godowns for the authenticated enterprise."""
    company = getattr(request.user, 'company', None)
    if not company:
        messages.error(request, "No enterprise profile associated with this account.")
        return redirect('index')

    locations = company.locations.all()
    return render(request, 'accounts/locations.html', {
        'company': company,
        'locations': locations,
        'is_supplier': company.can_sell,
    })


@login_required
def location_create(request):
    """Add a new godown or warehouse with interactive Leaflet map picker."""
    company = getattr(request.user, 'company', None)
    if not company:
        messages.error(request, "No enterprise profile associated with this account.")
        return redirect('index')

    default_redirect = 'supplier_dashboard' if company.can_sell else 'profile'
    next_url = request.GET.get('next') or request.POST.get('next') or default_redirect

    if request.method == 'POST':
        form = CompanyLocationForm(request.POST)
        if form.is_valid():
            loc = form.save(commit=False)
            loc.company = company
            loc.save()
            facility_type = loc.get_location_type_display()
            messages.success(request, f"{facility_type} '{loc.location_name}' registered successfully!")
            return redirect(next_url)
    else:
        default_type = 'warehouse' if company.can_sell else 'godown'
        form = CompanyLocationForm(initial={
            'location_type': default_type,
            'is_primary': not company.locations.exists()
        })

    return render(request, 'accounts/location_form.html', {
        'form': form,
        'company': company,
        'is_edit': False,
        'next_url': next_url,
        'is_supplier': company.can_sell,
    })


@login_required
def location_edit(request, pk):
    """Edit an existing warehouse or godown with interactive Leaflet map picker."""
    company = getattr(request.user, 'company', None)
    if not company:
        messages.error(request, "No enterprise profile associated with this account.")
        return redirect('index')

    loc = get_object_or_404(CompanyLocation, pk=pk, company=company)
    default_redirect = 'supplier_dashboard' if company.can_sell else 'profile'
    next_url = request.GET.get('next') or request.POST.get('next') or default_redirect

    if request.method == 'POST':
        form = CompanyLocationForm(request.POST, instance=loc)
        if form.is_valid():
            form.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                from django.http import JsonResponse
                return JsonResponse({
                    'status': 'success',
                    'message': f"Location '{loc.location_name}' updated successfully.",
                    'location': {
                        'id': loc.id,
                        'name': loc.location_name,
                        'address': loc.address,
                        'latitude': float(loc.latitude) if loc.latitude else None,
                        'longitude': float(loc.longitude) if loc.longitude else None,
                    }
                })
            messages.success(request, f"Location '{loc.location_name}' updated successfully.")
            return redirect(next_url)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                from django.http import JsonResponse
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
    else:
        form = CompanyLocationForm(instance=loc)

    return render(request, 'accounts/location_form.html', {
        'form': form,
        'location': loc,
        'company': company,
        'is_edit': True,
        'next_url': next_url,
        'is_supplier': company.can_sell,
    })


@login_required
def location_delete(request, pk):
    """
    Safely delete a facility, preventing deletion if referenced by active listings or pending orders.
    """
    company = getattr(request.user, 'company', None)
    if not company:
        messages.error(request, "No enterprise profile associated with this account.")
        return redirect('index')

    loc = get_object_or_404(CompanyLocation, pk=pk, company=company)
    default_redirect = 'supplier_dashboard' if company.can_sell else 'profile'
    next_url = request.GET.get('next') or default_redirect

    # Safety Check: Prevent deletion if active byproduct listings are stored at this warehouse
    active_listings_count = loc.listings.filter(is_active=True).count()
    if active_listings_count > 0:
        messages.warning(
            request,
            f"Cannot delete '{loc.location_name}': it is currently associated with {active_listings_count} active byproduct listing(s). "
            f"Please reassign those listings to another warehouse before deleting this location."
        )
        return redirect(next_url)

    # Safety Check: Prevent deletion if active/pending orders are destined for this godown
    active_deliveries_count = loc.deliveries.filter(status__in=['pending', 'accepted', 'partially_fulfilled']).count()
    if active_deliveries_count > 0:
        messages.warning(
            request,
            f"Cannot delete '{loc.location_name}': it is designated as the delivery facility for {active_deliveries_count} active procurement order(s). "
            f"Orders must be completed before removing this facility."
        )
        return redirect(next_url)

    was_primary = loc.is_primary
    loc_name = loc.location_name
    loc.delete()

    # If the removed location was primary, promote remaining location
    if was_primary:
        next_loc = company.locations.first()
        if next_loc:
            next_loc.is_primary = True
            next_loc.save(update_fields=['is_primary'])

    messages.success(request, f"Location '{loc_name}' has been successfully removed.")
    return redirect(next_url)


@login_required
def location_set_primary(request, pk):
    """Designates a godown or warehouse as the primary operating facility."""
    company = getattr(request.user, 'company', None)
    if not company:
        messages.error(request, "No enterprise profile associated with this account.")
        return redirect('index')

    loc = get_object_or_404(CompanyLocation, pk=pk, company=company)
    default_redirect = 'supplier_dashboard' if company.can_sell else 'profile'
    next_url = request.GET.get('next') or default_redirect

    loc.is_primary = True
    loc.save()
    messages.success(request, f"'{loc.location_name}' is now your designated primary {loc.get_location_type_display()}.")
    return redirect(next_url)
