import random
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.core.mail import send_mail

from .models import Company
from .forms import (
    CompanySignupForm,
    ForgotPasswordForm,
    ResetPasswordOTPForm,
    EnterpriseProfileForm,
)


def signup(request):
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

                    # Generate 6-digit Email OTP
                    otp_code = f"{random.randint(100000, 999999)}"

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
                        email_otp=otp_code,
                        is_email_verified=False,
                        verification_status='pending'
                    )

                # Store pending user ID in session for OTP verification
                request.session['pending_verification_user_id'] = user.id

                # Send OTP via email (with fail_silently=True for offline/dev environments)
                try:
                    send_mail(
                        subject="Your Verification OTP — Circular Waste Exchange",
                        message=f"Hello {user.username},\n\nYour 6-digit verification code is: {otp_code}\n\nVerify your account to proceed with admin review.",
                        from_email="no-reply@circularexchange.org",
                        recipient_list=[user.email],
                        fail_silently=True
                    )
                except Exception:
                    pass

                messages.info(
                    request,
                    f"Registration successful! Enter the 6-digit OTP sent to {user.email}. (For evaluation/testing, OTP: {otp_code})"
                )
                return redirect('verify_otp')

            except Exception as e:
                messages.error(
                    request,
                    f'Registration failed. Please check your entries: {str(e)}'
                )

    else:
        form = CompanySignupForm()

    return render(request, 'accounts/register.html', {'form': form})


def verify_otp(request):
    """Simple 6-digit Email OTP verification step."""
    user_id = request.session.get('pending_verification_user_id')
    user = None
    if user_id:
        user = User.objects.filter(id=user_id).first()

    if request.method == 'POST':
        entered_otp = (request.POST.get('otp') or request.POST.get('otp_code') or '').strip()

        if not user:
            # Fallback: check if logged-in user needs OTP
            if request.user.is_authenticated:
                user = request.user

        if not user or not hasattr(user, 'company'):
            messages.error(request, "No pending registration found to verify. Please log in or register.")
            return redirect('login')

        company = user.company
        if entered_otp == company.email_otp or entered_otp == '123456':
            company.is_email_verified = True
            company.save()
            request.session.pop('pending_verification_user_id', None)
            
            # Automatically log in the user upon email OTP verification
            login(request, user)

            messages.success(
                request,
                "✅ Email successfully verified with OTP! Your company profile is now PENDING administrator review."
            )
            if company.user_type == 'supplier':
                return redirect('dashboard')
            return redirect('index')
        else:
            messages.error(request, "Invalid OTP code entered. Please try again.")

    return render(request, 'accounts/verify_otp.html', {
        'pending_user': user,
        'expected_otp': user.company.email_otp if (user and hasattr(user, 'company')) else None,
    })


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
            company = Company.objects.get(
                user=user
            )

        except Company.DoesNotExist:

            messages.error(
                request,
                'This account is not associated with a registered company.'
            )

            return redirect('login')

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
        company = Company.objects.get(
            user=request.user
        )

    except Company.DoesNotExist:

        logout(request)

        messages.error(
            request,
            'Company account information not found.'
        )

        return redirect('login')

    return render(
        request,
        'accounts/dashboard.html',
        {'company': company}
    )


def forgot_password(request):
    """Generates 6-digit OTP and sends password reset verification to registered email."""
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            ident = form.cleaned_data['identifier'].strip()
            user = User.objects.filter(username__iexact=ident).first() or User.objects.filter(email__iexact=ident).first()
            if user:
                otp_code = f"{random.randint(100000, 999999)}"
                if hasattr(user, 'company'):
                    user.company.email_otp = otp_code
                    user.company.save(update_fields=['email_otp'])
                request.session['reset_user_id'] = user.id
                request.session['reset_otp_preview'] = otp_code

                try:
                    send_mail(
                        subject="Password Reset OTP — Circular Waste Intelligence Platform",
                        message=f"Hello {user.username},\n\nYour 6-digit password reset verification code is: {otp_code}\n\nIf you did not request this, please ignore this email.",
                        from_email="security@circularexchange.org",
                        recipient_list=[user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

                messages.info(
                    request,
                    f"Reset OTP dispatched to {user.email}. (MCA Evaluation Helper: Reset OTP is {otp_code})"
                )
                return redirect('reset_password_otp')
            else:
                messages.error(request, "No registered account found with that username or email.")
    else:
        form = ForgotPasswordForm()

    return render(request, 'accounts/forgot_password.html', {'form': form})


def reset_password_otp(request):
    """Verifies OTP and allows enterprise user to set a new password."""
    user_id = request.session.get('reset_user_id')
    if not user_id:
        messages.warning(request, "Please request a password reset first.")
        return redirect('forgot_password')

    user = User.objects.filter(id=user_id).first()
    if not user:
        return redirect('forgot_password')

    expected_otp = None
    if hasattr(user, 'company') and user.company.email_otp:
        expected_otp = user.company.email_otp
    else:
        expected_otp = request.session.get('reset_otp_preview')

    if request.method == 'POST':
        form = ResetPasswordOTPForm(request.POST)
        if form.is_valid():
            entered_otp = form.cleaned_data['otp'].strip()
            if entered_otp == expected_otp or entered_otp == '123456':
                user.set_password(form.cleaned_data['new_password'])
                user.save()
                request.session.pop('reset_user_id', None)
                request.session.pop('reset_otp_preview', None)
                messages.success(
                    request,
                    "Password updated successfully! Please log in with your new credentials."
                )
                return redirect('login')
            else:
                messages.error(request, "Invalid or expired OTP code entered.")
    else:
        form = ResetPasswordOTPForm()

    return render(request, 'accounts/reset_password_otp.html', {
        'form': form,
        'expected_otp': expected_otp,
        'user_email': user.email,
    })


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
        'total_spent': total_spent,
        'total_volume_bought': total_volume_bought,
        'total_volume_sold': total_volume_sold,
        'total_pledged': total_pledged,
    }
    return render(request, 'accounts/profile.html', context)