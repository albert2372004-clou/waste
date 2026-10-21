from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import Company, CompanyLocation
from accounts.services.otp_service import (
    send_registration_otp,
    verify_registration_otp,
    can_resend_registration_otp,
    send_password_reset_otp,
    verify_password_reset_otp,
    can_resend_password_reset_otp,
)


class RegistrationAndAuthenticationOTPTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_registration_generates_and_dispatches_otp(self):
        """Tests registration workflow: creates unverified user and sends 6-digit OTP."""
        mail.outbox.clear()
        permit_file = SimpleUploadedFile("permit.pdf", b"%PDF-1.4 dummy permit content", content_type="application/pdf")
        data = {
            'username': 'rubber_corp',
            'email': 'contact@rubbercorp.com',
            'password': 'StrongPassword123#',
            'confirm_password': 'StrongPassword123#',
            'company_name': 'Rubber Corp Ltd',
            'registration_number': 'REG-RC-101',
            'gstin': '32AABCR1010M1Z1',
            'authorized_person': 'Ramesh Kumar',
            'phone': '9846011111',
            'address': 'Industrial Estate, Kottayam, Kerala',
            'user_type': 'supplier',
            'permit_document': permit_file,
        }
        response = self.client.post('/signup/', data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/verify-otp/')

        # User and company created
        user = User.objects.filter(username='rubber_corp').first()
        self.assertIsNotNone(user)
        company = user.company
        self.assertFalse(company.is_email_verified)
        self.assertEqual(company.verification_status, 'pending')
        self.assertEqual(len(company.email_otp), 6)
        self.assertTrue(company.email_otp.isdigit())

        # Email sent via mail backend
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(company.email_otp, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['contact@rubbercorp.com'])

    def test_correct_otp_verifies_registration_and_redirects_to_login(self):
        """Correct OTP marks email verified, single-use clears OTP, preserves pending status, and redirects to login."""
        user = User.objects.create_user(username='test_user', email='test@example.com', password='Password123#')
        company = Company.objects.create(
            user=user,
            company_name='Test Company',
            registration_number='REG-TEST-01',
            gstin='32AABCT0001M1Z1',
            user_type='supplier',
            is_email_verified=False,
            verification_status='pending',
            email_otp='654321',
            otp_created_at=timezone.now(),
            otp_attempts=0
        )
        session = self.client.session
        session['pending_verification_user_id'] = user.id
        session.save()

        response = self.client.post('/verify-otp/', {'otp': '654321'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/login/')

        company.refresh_from_db()
        self.assertTrue(company.is_email_verified)
        self.assertEqual(company.email_otp, '')  # Single-use cleared
        self.assertEqual(company.verification_status, 'pending')  # Preserved!

    def test_incorrect_otp_increments_attempts_and_locks_out(self):
        """Incorrect OTP increments attempt counter and locks out after 5 attempts."""
        user = User.objects.create_user(username='lock_user', email='lock@example.com', password='Password123#')
        company = Company.objects.create(
            user=user,
            company_name='Lock Company',
            registration_number='REG-LOCK-01',
            gstin='32AABCL0001M1Z1',
            user_type='supplier',
            is_email_verified=False,
            verification_status='pending',
            email_otp='123456',
            otp_created_at=timezone.now(),
            otp_attempts=0
        )
        session = self.client.session
        session['pending_verification_user_id'] = user.id
        session.save()

        # Submit 4 incorrect attempts
        for i in range(1, 5):
            res = self.client.post('/verify-otp/', {'otp': '000000'})
            self.assertEqual(res.status_code, 200)
            company.refresh_from_db()
            self.assertFalse(company.is_email_verified)
            self.assertEqual(company.otp_attempts, i)
            self.assertEqual(company.email_otp, '123456')

        # 5th incorrect attempt locks out and invalidates OTP
        res5 = self.client.post('/verify-otp/', {'otp': '000000'})
        self.assertEqual(res5.status_code, 200)
        company.refresh_from_db()
        self.assertEqual(company.email_otp, '')
        self.assertFalse(company.is_email_verified)

    def test_expired_otp_is_rejected(self):
        """OTP older than 10 minutes is rejected and cleared."""
        user = User.objects.create_user(username='exp_user', email='exp@example.com', password='Password123#')
        company = Company.objects.create(
            user=user,
            company_name='Exp Company',
            registration_number='REG-EXP-01',
            gstin='32AABCE0001M1Z1',
            user_type='buyer',
            is_email_verified=False,
            verification_status='pending',
            email_otp='888999',
            otp_created_at=timezone.now() - timedelta(minutes=11),
            otp_attempts=0
        )
        session = self.client.session
        session['pending_verification_user_id'] = user.id
        session.save()

        response = self.client.post('/verify-otp/', {'otp': '888999'})
        self.assertEqual(response.status_code, 200)
        company.refresh_from_db()
        self.assertFalse(company.is_email_verified)
        self.assertEqual(company.email_otp, '')

    def test_reused_otp_is_rejected(self):
        """A used OTP cannot be reused because it is wiped upon successful verification."""
        user = User.objects.create_user(username='reuse_user', email='reuse@example.com', password='Password123#')
        company = Company.objects.create(
            user=user,
            company_name='Reuse Company',
            registration_number='REG-REU-01',
            gstin='32AABCR0001M1Z1',
            user_type='buyer',
            is_email_verified=False,
            verification_status='pending',
            email_otp='555666',
            otp_created_at=timezone.now(),
            otp_attempts=0
        )
        session = self.client.session
        session['pending_verification_user_id'] = user.id
        session.save()

        # First verification succeeds
        r1 = self.client.post('/verify-otp/', {'otp': '555666'})
        self.assertEqual(r1.status_code, 302)

        # Attempt to verify again with the same code
        session['pending_verification_user_id'] = user.id
        session.save()
        r2 = self.client.post('/verify-otp/', {'otp': '555666'})
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "No active verification code found")

    def test_resend_otp_cooldown(self):
        """Enforces 60-second cooldown on OTP resending."""
        user = User.objects.create_user(username='cool_user', email='cool@example.com', password='Password123#')
        company = Company.objects.create(
            user=user,
            company_name='Cooldown Co',
            registration_number='REG-CD-01',
            gstin='32AABCD0001M1Z1',
            user_type='buyer',
            is_email_verified=False,
            verification_status='pending',
            email_otp='111222',
            otp_created_at=timezone.now(),  # just now
            otp_attempts=0
        )
        session = self.client.session
        session['pending_verification_user_id'] = user.id
        session.save()

        mail.outbox.clear()
        # Immediate resend should be blocked by cooldown
        res_blocked = self.client.get('/resend-otp/')
        self.assertEqual(res_blocked.status_code, 302)
        self.assertRedirects(res_blocked, '/verify-otp/')
        self.assertEqual(len(mail.outbox), 0)

        # Advance time by 61 seconds
        company.otp_created_at = timezone.now() - timedelta(seconds=65)
        company.save(update_fields=['otp_created_at'])

        res_allowed = self.client.get('/resend-otp/')
        self.assertEqual(res_allowed.status_code, 302)
        self.assertRedirects(res_allowed, '/verify-otp/')
        self.assertEqual(len(mail.outbox), 1)

    def test_unverified_user_cannot_login_redirects_to_verify_otp(self):
        """Unverified email accounts cannot log in and are redirected to verify_otp."""
        user = User.objects.create_user(username='unver_login', email='unver@co.com', password='Password123#')
        Company.objects.create(
            user=user,
            company_name='Unver Login Co',
            registration_number='REG-UNV-01',
            gstin='32AABCU0001M1Z1',
            user_type='supplier',
            is_email_verified=False,
            verification_status='pending'
        )

        response = self.client.post('/login/', {'username': 'unver_login', 'password': 'Password123#'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/verify-otp/')
        self.assertNotIn('_auth_user_id', self.client.session)


class ForgotPasswordAndResetOTPTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='reset_user', email='reset@example.com', password='OldPassword123#')
        self.company = Company.objects.create(
            user=self.user,
            company_name='Reset Company',
            registration_number='REG-RST-01',
            gstin='32AABCR9999M1Z9',
            user_type='supplier',
            is_email_verified=True,
            verification_status='pending'
        )

    def test_forgot_password_generic_response_registered_user(self):
        """Registered user receives reset OTP email and generic message to prevent enumeration."""
        mail.outbox.clear()
        response = self.client.post('/forgot-password/', {'identifier': 'reset_user'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/reset-password-otp/')

        self.company.refresh_from_db()
        self.assertEqual(len(self.company.reset_otp), 6)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.company.reset_otp, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['reset@example.com'])

    def test_forgot_password_generic_response_unregistered_user(self):
        """Non-existing identifier yields the exact same redirect and generic message without dispatching email."""
        mail.outbox.clear()
        response = self.client.post('/forgot-password/', {'identifier': 'non_existent_account'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/reset-password-otp/')
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_password_otp_success_updates_password_and_preserves_company_status(self):
        """Step 1 verifies OTP and redirects to set_new_password; Step 2 sets password and redirects to login."""
        self.company.reset_otp = '777888'
        self.company.reset_otp_created_at = timezone.now()
        self.company.reset_otp_attempts = 0
        self.company.verification_status = 'pending'
        self.company.save()

        session = self.client.session
        session['reset_user_id'] = self.user.id
        session.save()

        # Step 1: Verify OTP only
        response = self.client.post('/reset-password-otp/', {'otp': '777888'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/set-new-password/')

        # Step 2: Set new password
        session = self.client.session
        self.assertTrue(session.get('reset_otp_verified'))

        pw_resp = self.client.post('/set-new-password/', {
            'new_password': 'NewStrongPassword456#',
            'confirm_password': 'NewStrongPassword456#',
        })
        self.assertEqual(pw_resp.status_code, 302)
        self.assertRedirects(pw_resp, '/login/')

        # Old password must no longer authenticate
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('OldPassword123#'))
        self.assertTrue(self.user.check_password('NewStrongPassword456#'))

        # Single-use reset OTP cleared
        self.company.refresh_from_db()
        self.assertEqual(self.company.reset_otp, '')
        # Company approval status must NOT be changed!
        self.assertEqual(self.company.verification_status, 'pending')

    def test_reset_password_weak_password_rejected(self):
        """Weak password fails Django password validation on set_new_password."""
        session = self.client.session
        session['reset_user_id'] = self.user.id
        session['reset_otp_verified'] = True
        session.save()

        data = {
            'new_password': '123',
            'confirm_password': '123',
        }
        response = self.client.post('/set-new-password/', data)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        # Password unchanged
        self.assertTrue(self.user.check_password('OldPassword123#'))

    def test_reset_password_incorrect_otp_and_lockout(self):
        """Incorrect reset OTP increments attempts and locks out at 5."""
        self.company.reset_otp = '999111'
        self.company.reset_otp_created_at = timezone.now()
        self.company.reset_otp_attempts = 0
        self.company.save()

        session = self.client.session
        session['reset_user_id'] = self.user.id
        session.save()

        for i in range(1, 5):
            res = self.client.post('/reset-password-otp/', {'otp': '000000'})
            self.assertEqual(res.status_code, 200)
            self.company.refresh_from_db()
            self.assertEqual(self.company.reset_otp_attempts, i)
            self.assertEqual(self.company.reset_otp, '999111')

        # 5th attempt invalidates reset code
        res5 = self.client.post('/reset-password-otp/', {'otp': '000000'})
        self.assertEqual(res5.status_code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.reset_otp, '')

    def test_reset_password_resend_cooldown(self):
        """Enforces 60-second cooldown on password reset OTP resend."""
        self.company.reset_otp = '123123'
        self.company.reset_otp_created_at = timezone.now()
        self.company.save()

        session = self.client.session
        session['reset_user_id'] = self.user.id
        session.save()

        mail.outbox.clear()
        res_blocked = self.client.get('/resend-reset-otp/')
        self.assertEqual(res_blocked.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

        # Advance time by 65 seconds
        self.company.reset_otp_created_at = timezone.now() - timedelta(seconds=65)
        self.company.save(update_fields=['reset_otp_created_at'])

        res_allowed = self.client.get('/resend-reset-otp/')
        self.assertEqual(res_allowed.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)


class ExistingAccountsWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_dual_role_mode_switching(self):
        """Dual-Role enterprises can switch between buyer and supplier modes."""
        user = User.objects.create_user(username='dual_user', email='dual@corp.com', password='Password123#')
        Company.objects.create(
            user=user,
            company_name='Dual Enterprise Ltd',
            registration_number='REG-DUAL-01',
            gstin='32AABCD1111M1Z5',
            user_type='both',
            verification_status='auto_verified',
            is_email_verified=True
        )
        self.client.force_login(user)

        resp_sup = self.client.get('/switch-mode/supplier/')
        self.assertEqual(resp_sup.status_code, 302)
        self.assertEqual(self.client.session.get('active_mode'), 'supplier')

        resp_buy = self.client.get('/switch-mode/buyer/')
        self.assertEqual(resp_buy.status_code, 302)
        self.assertEqual(self.client.session.get('active_mode'), 'buyer')

    def test_pending_company_cannot_login_until_approved(self):
        """Verified email but pending company is not allowed into marketplace."""
        user = User.objects.create_user(username='pending_co', email='p@co.com', password='Password123#')
        Company.objects.create(
            user=user,
            company_name='Pending Co',
            registration_number='REG-PEND-01',
            gstin='32AABCP0001M1Z1',
            authorized_person='Officer',
            phone='9846000001',
            address='Industrial Zone, Aluva, Kerala',
            user_type='supplier',
            is_email_verified=True,
            verification_status='pending'
        )

        response = self.client.post('/login/', {'username': 'pending_co', 'password': 'Password123#'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/login/')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_verified_supplier_redirects_to_dashboard(self):
        """Verified supplier logs in and redirects to supplier dashboard."""
        user = User.objects.create_user(username='verified_supplier', email='s@co.com', password='Password123#')
        Company.objects.create(
            user=user,
            company_name='Verified Supplier Ltd',
            registration_number='REG-VER-02',
            gstin='32AABCS0002M1Z2',
            authorized_person='Manager',
            phone='9846000002',
            address='Kottayam Industrial Estate, Kerala',
            user_type='supplier',
            is_email_verified=True,
            verification_status='manual_approved'
        )

        response = self.client.post('/login/', {'username': 'verified_supplier', 'password': 'Password123#'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/dashboard/')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_verified_buyer_redirects_to_marketplace(self):
        """Verified buyer logs in and redirects to marketplace index."""
        user = User.objects.create_user(username='verified_buyer', email='b@co.com', password='Password123#')
        Company.objects.create(
            user=user,
            company_name='Verified Buyer Corp',
            registration_number='REG-BUY-03',
            gstin='32AABCB0003M1Z3',
            authorized_person='Procurement Lead',
            phone='9846000003',
            address='Kochi Logistics Hub, Kerala',
            user_type='buyer',
            is_email_verified=True,
            verification_status='auto_verified'
        )

        response = self.client.post('/login/', {'username': 'verified_buyer', 'password': 'Password123#'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_admin_verification_hub_actions(self):
        """Platform admin can flag, approve, or reject companies."""
        admin_user = User.objects.create_superuser(username='admin_boss', email='admin@platform.com', password='AdminPassword123#')
        user = User.objects.create_user(username='vendor_review', email='v@r.com', password='Password123#')
        company = Company.objects.create(
            user=user,
            company_name='Palakkad Recyclers',
            registration_number='REG-PKD-44',
            gstin='32AABCP4444M1Z4',
            authorized_person='Director',
            phone='9846000044',
            address='KINFRA Park, Palakkad, Kerala',
            user_type='supplier',
            is_email_verified=True,
            verification_status='pending'
        )

        self.client.force_login(admin_user)
        # Test Flag action
        r_flag = self.client.post('/verification/', {'company_id': company.id, 'action': 'flag'})
        self.assertEqual(r_flag.status_code, 302)
        company.refresh_from_db()
        self.assertEqual(company.verification_status, 'flagged')

        # Test Approve action
        r_approve = self.client.post('/verification/', {'company_id': company.id, 'action': 'approve'})
        self.assertEqual(r_approve.status_code, 302)
        company.refresh_from_db()
        self.assertEqual(company.verification_status, 'manual_approved')
        self.assertTrue(company.is_verified)

        # Test Reject action
        r_reject = self.client.post('/verification/', {'company_id': company.id, 'action': 'reject'})
        self.assertEqual(r_reject.status_code, 302)
        company.refresh_from_db()
        self.assertEqual(company.verification_status, 'rejected')
        self.assertFalse(company.is_verified)


class LocationManagementAndNavbarTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Buyer
        self.buyer_user = User.objects.create_user(
            username='cochin_buyer',
            email='buyer@cochinrec.com',
            password='Password123#'
        )
        self.buyer_company = Company.objects.create(
            user=self.buyer_user,
            company_name='Cochin Polymers',
            registration_number='REG-BUYER-01',
            gstin='32AABCB1111M1Z1',
            user_type='buyer',
            is_email_verified=True,
            verification_status='auto_verified',
            address='Kaloor, Kochi, Kerala'
        )

        # Supplier
        self.supplier_user = User.objects.create_user(
            username='kottayam_sup',
            email='supplier@kottayamrub.com',
            password='Password123#'
        )
        self.supplier_company = Company.objects.create(
            user=self.supplier_user,
            company_name='Kottayam Rubber Corp',
            registration_number='REG-SUP-01',
            gstin='32AABCS2222M1Z2',
            user_type='supplier',
            is_email_verified=True,
            verification_status='auto_verified',
            address='Rubber Board Road, Kottayam, Kerala'
        )

    def test_buyer_profile_displays_godowns_section_and_locations(self):
        """Buyer profile renders Manage My Godowns section with registered godowns."""
        loc = CompanyLocation.objects.create(
            company=self.buyer_company,
            location_name='Aluva Godown 1',
            location_type='godown',
            address='Near Metro Pillar 250, Aluva, Ernakulam',
            latitude=10.1076,
            longitude=76.3516,
            is_primary=True
        )
        self.client.force_login(self.buyer_user)
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manage My Godowns')
        self.assertContains(response, 'Aluva Godown 1')
        self.assertContains(response, 'Near Metro Pillar 250')
        self.assertContains(response, '10.1076')

    def test_supplier_profile_and_dashboard_displays_warehouses(self):
        """Supplier profile and dashboard render warehouse listings."""
        loc = CompanyLocation.objects.create(
            company=self.supplier_company,
            location_name='Kottayam Main Warehouse',
            location_type='warehouse',
            address='Industrial Estate, Kottayam',
            latitude=9.5916,
            longitude=76.5222,
            is_primary=True
        )
        self.client.force_login(self.supplier_user)
        # Profile
        profile_res = self.client.get('/profile/')
        self.assertEqual(profile_res.status_code, 200)
        self.assertContains(profile_res, 'Manage My Warehouses')
        self.assertContains(profile_res, 'Kottayam Main Warehouse')

        # Dashboard
        dash_res = self.client.get('/dashboard/')
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, 'Factory &amp; Warehouse Facilities')
        self.assertContains(dash_res, 'Kottayam Main Warehouse')

    def test_buyer_create_location_valid(self):
        """Buyer can create a godown via /locations/create/."""
        self.client.force_login(self.buyer_user)
        data = {
            'location_name': 'Kalamassery Storage Hub',
            'location_type': 'godown',
            'address': 'Kinfra Hi-Tech Park, Kalamassery',
            'latitude': '10.0520000',
            'longitude': '76.3270000',
            'is_primary': True
        }
        response = self.client.post('/locations/create/', data)
        self.assertEqual(response.status_code, 302)
        loc = CompanyLocation.objects.filter(company=self.buyer_company, location_name='Kalamassery Storage Hub').first()
        self.assertIsNotNone(loc)
        self.assertEqual(float(loc.latitude), 10.052)
        self.assertEqual(float(loc.longitude), 76.327)
        self.assertTrue(loc.is_primary)

    def test_location_validation_rejects_out_of_range_coordinates(self):
        """Form validation strictly rejects out-of-range coordinates."""
        self.client.force_login(self.buyer_user)
        data = {
            'location_name': 'Invalid Coordinates Hub',
            'location_type': 'godown',
            'address': 'Nowhere',
            'latitude': '195.0',  # Latitude > 90 invalid
            'longitude': '76.32',
        }
        response = self.client.post('/locations/create/', data)
        self.assertEqual(response.status_code, 200)  # Re-renders form with errors
        self.assertFalse(CompanyLocation.objects.filter(location_name='Invalid Coordinates Hub').exists())

    def test_location_edit_ajax_returns_json(self):
        """Editing location via AJAX returns updated JSON data without full reload."""
        loc = CompanyLocation.objects.create(
            company=self.buyer_company,
            location_name='Angamaly Facility',
            location_type='godown',
            address='Angamaly Bypass',
            latitude=10.1960,
            longitude=76.3860,
            is_primary=True
        )
        self.client.force_login(self.buyer_user)
        edit_data = {
            'location_name': 'Angamaly Central Hub',
            'location_type': 'godown',
            'address': 'Angamaly South, Ernakulam',
            'latitude': '10.1985000',
            'longitude': '76.3892000',
            'is_ajax': '1',
        }
        response = self.client.post(
            f'/locations/{loc.pk}/edit/',
            edit_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['location']['name'], 'Angamaly Central Hub')

        loc.refresh_from_db()
        self.assertEqual(loc.location_name, 'Angamaly Central Hub')
        self.assertEqual(float(loc.latitude), 10.1985)

    def test_company_location_isolation_prevents_unauthorized_access(self):
        """Users cannot edit or delete locations belonging to another company."""
        supplier_loc = CompanyLocation.objects.create(
            company=self.supplier_company,
            location_name='Secret Rubber Yard',
            location_type='warehouse',
            address='Kottayam Deep Forest',
            latitude=9.58,
            longitude=76.51
        )
        # Buyer attempts to edit supplier's location
        self.client.force_login(self.buyer_user)
        response = self.client.get(f'/locations/{supplier_loc.pk}/edit/')
        self.assertEqual(response.status_code, 404)

        del_res = self.client.post(f'/locations/{supplier_loc.pk}/delete/')
        self.assertEqual(del_res.status_code, 404)
        self.assertTrue(CompanyLocation.objects.filter(pk=supplier_loc.pk).exists())

    def test_single_primary_location_constraint(self):
        """Setting a location as primary automatically clears previous primary."""
        loc1 = CompanyLocation.objects.create(
            company=self.buyer_company,
            location_name='Godown 1',
            location_type='godown',
            address='Address 1',
            is_primary=True
        )
        loc2 = CompanyLocation.objects.create(
            company=self.buyer_company,
            location_name='Godown 2',
            location_type='godown',
            address='Address 2',
            is_primary=True
        )
        loc1.refresh_from_db()
        loc2.refresh_from_db()
        self.assertFalse(loc1.is_primary)
        self.assertTrue(loc2.is_primary)

    def test_navbar_renders_correctly_for_all_roles(self):
        """Navbar displays responsive elements, search, corridor info, and role-specific links."""
        # Anonymous visitor
        res_anon = self.client.get('/')
        self.assertContains(res_anon, 'Kerala Industrial Corridor')
        self.assertContains(res_anon, 'Search material, byproduct, or supplier...')
        self.assertContains(res_anon, 'Login')
        self.assertContains(res_anon, 'Register')

        # Buyer
        self.client.force_login(self.buyer_user)
        res_buyer = self.client.get('/')
        self.assertContains(res_buyer, 'Kerala Industrial Corridor')
        self.assertContains(res_buyer, '📦 Orders')
        self.assertContains(res_buyer, '🛒 Cart')
        self.assertContains(res_buyer, 'Profile')
        self.assertContains(res_buyer, 'Logout')

        # Supplier
        self.client.force_login(self.supplier_user)
        res_sup = self.client.get('/')
        self.assertContains(res_sup, 'Kerala Industrial Corridor')
        self.assertContains(res_sup, 'Supplier Hub')
        self.assertContains(res_sup, '+ List Waste')
        self.assertContains(res_sup, 'Profile')
        self.assertContains(res_sup, 'Logout')

    def test_godown_form_renders_visible_map_and_osm_tile_config(self):
        """Godown add and edit forms visibly render the interactive OpenStreetMap Leaflet container."""
        self.client.force_login(self.buyer_user)

        # 1. Add Form
        res_create = self.client.get('/locations/create/')
        self.assertEqual(res_create.status_code, 200)
        self.assertContains(res_create, 'godown-map-canvas')
        self.assertContains(res_create, 'leaflet.js')
        self.assertContains(res_create, 'tile.openstreetmap.org')
        self.assertContains(res_create, 'godown-map-search-input')
        self.assertContains(res_create, 'godown-map-coords-badge')

        # 2. Edit Form
        loc = CompanyLocation.objects.create(
            company=self.buyer_company,
            location_name='Kochi Export Godown',
            location_type='godown',
            address='Willingdon Island, Kochi',
            latitude=9.9650,
            longitude=76.2700,
            is_primary=True
        )
        res_edit = self.client.get(f'/locations/{loc.pk}/edit/')
        self.assertEqual(res_edit.status_code, 200)
        self.assertContains(res_edit, 'godown-map-canvas')
        self.assertContains(res_edit, '9.9650')
        self.assertContains(res_edit, '76.2700')

    def test_supplier_listing_create_shows_only_own_warehouses(self):
        """Supplier waste listing creation form lists ONLY the logged-in supplier's warehouses."""
        # Create warehouse for supplier 1
        sup1_loc = CompanyLocation.objects.create(
            company=self.supplier_company,
            location_name='Supplier 1 Primary Warehouse',
            location_type='warehouse',
            address='Rubber Road, Kottayam',
            latitude=9.59,
            longitude=76.52,
            is_primary=True
        )

        # Create another supplier with their own warehouse
        other_user = User.objects.create_user(username='other_supplier', password='Password123#')
        other_company = Company.objects.create(
            user=other_user,
            company_name='Other Waste Generator',
            registration_number='REG-OTH-99',
            gstin='32AABCO9999M1Z9',
            user_type='supplier',
            is_email_verified=True,
            verification_status='auto_verified'
        )
        other_loc = CompanyLocation.objects.create(
            company=other_company,
            location_name='Other Supplier Secret Facility',
            location_type='warehouse',
            address='Alappuzha Waterway',
            latitude=9.49,
            longitude=76.33,
            is_primary=True
        )

        self.client.force_login(self.supplier_user)
        response = self.client.get('/supplier/listings/create/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Supplier 1 Primary Warehouse')
        self.assertNotContains(response, 'Other Supplier Secret Facility')

    def test_buyer_without_godowns_blocked_from_ordering_with_warning(self):
        """Buyers without any registered destination godowns cannot place orders and are redirected to register one."""
        from decimal import Decimal
        from marketplace.models import MaterialCategory, MaterialListing

        cat, _ = MaterialCategory.objects.get_or_create(code='rubber', defaults={'name': 'Rubber', 'standard_price_per_ton': Decimal('20000.00')})
        sup_loc = CompanyLocation.objects.create(
            company=self.supplier_company,
            location_name='Pickup Depot',
            location_type='warehouse',
            address='Depot Road, Kottayam',
            latitude=9.59,
            longitude=76.52,
            is_primary=True
        )
        listing = MaterialListing.objects.create(
            supplier=self.supplier_company,
            warehouse=sup_loc,
            material_name='Rubber Scrap',
            category='rubber',
            category_ref=cat,
            price_per_ton=Decimal('15000.00'),
            volume_tons=Decimal('50.00'),
            moq_tons=Decimal('5.00'),
            approval_status='approved',
            is_active=True
        )

        # Create buyer with NO godowns
        empty_buyer_user = User.objects.create_user(username='empty_buyer', password='Password123#')
        Company.objects.create(
            user=empty_buyer_user,
            company_name='Godownless Buyer Corp',
            registration_number='REG-NOGODOWN-01',
            gstin='32AABCN0001M1Z1',
            user_type='buyer',
            is_email_verified=True,
            verification_status='auto_verified'
        )

        self.client.force_login(empty_buyer_user)

        # Direct checkout
        res_checkout = self.client.post(f'/checkout/{listing.pk}/', {'volume_requested': '10.00'})
        self.assertEqual(res_checkout.status_code, 302)
        self.assertIn('/locations/create/', res_checkout.url)

        # Cart page displays required warning
        res_cart = self.client.get('/cart/')
        self.assertEqual(res_cart.status_code, 200)
        self.assertContains(res_cart, 'Destination Godown Required')
        self.assertContains(res_cart, 'Register Delivery Godown')


