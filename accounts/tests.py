from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import Company
from accounts.services.verification import verify_company_registration, is_valid_registration_structure


class AccountsAuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_company_registration_auto_verified(self):
        permit_file = SimpleUploadedFile("kspcb_permit.pdf", b"%PDF-1.4 dummy environmental permit content", content_type="application/pdf")
        data = {
            'username': 'kottayam_reprocessors',
            'email': 'contact@kottayamrubber.com',
            'password': 'StrongPassword123#',
            'confirm_password': 'StrongPassword123#',
            'company_name': 'Kottayam Rubber Reprocessors',
            'registration_number': 'REG-KL-2291',
            'gstin': '32AABCK2291M1Z8',
            'authorized_person': 'Rajesh Menon',
            'phone': '9846012345',
            'address': 'Plot 44, Industrial Estate, Kottayam, Kerala',
            'user_type': 'supplier',
            'permit_document': permit_file,
        }
        response = self.client.post('/signup/', data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/verify-otp/')

        # Submit OTP to complete email verification
        otp_response = self.client.post('/verify-otp/', {'otp_code': '123456'})
        self.assertEqual(otp_response.status_code, 302)
        self.assertRedirects(otp_response, '/dashboard/')

        company = Company.objects.filter(registration_number='REG-KL-2291').first()
        self.assertIsNotNone(company)
        self.assertTrue(company.is_email_verified)
        # Newly registered company with verified email goes to 'pending' for admin review
        self.assertEqual(company.verification_status, 'pending')

        # Admin reviews and approves the company
        admin_user = User.objects.create_superuser(username='admin_reviewer', email='admin@rev.com', password='AdminPassword123#')
        self.client.force_login(admin_user)
        self.client.post('/verification/', {'company_id': company.id, 'action': 'approve'})
        company.refresh_from_db()
        self.assertEqual(company.verification_status, 'manual_approved')
        self.assertTrue(company.is_verified)

    def test_registration_without_permit_is_pending(self):
        data = {
            'username': 'unverified_vendor',
            'email': 'unverified@vendor.com',
            'password': 'StrongPassword123#',
            'confirm_password': 'StrongPassword123#',
            'company_name': 'Unverified Vendor Corp',
            'registration_number': 'REG-NOPRM-01',
            'gstin': '32AABCV9999M1Z9',
            'authorized_person': 'Operator',
            'phone': '9846099999',
            'address': 'Industrial Zone, Kochi, Kerala',
            'user_type': 'supplier',
        }
        response = self.client.post('/signup/', data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/verify-otp/')
        company = Company.objects.filter(registration_number='REG-NOPRM-01').first()
        self.assertIsNotNone(company)
        self.assertEqual(company.verification_status, 'pending')
        self.assertFalse(company.is_verified)

    def test_dual_role_mode_switching(self):
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

        # Switch to supplier mode
        resp_sup = self.client.get('/switch-mode/supplier/')
        self.assertEqual(resp_sup.status_code, 302)
        self.assertEqual(self.client.session.get('active_mode'), 'supplier')

        # Switch to buyer mode
        resp_buy = self.client.get('/switch-mode/buyer/')
        self.assertEqual(resp_buy.status_code, 302)
        self.assertEqual(self.client.session.get('active_mode'), 'buyer')

    def test_unverified_company_cannot_login(self):
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
            verification_status='pending'
        )

        response = self.client.post('/login/', {'username': 'pending_co', 'password': 'Password123#'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/login/')
        # Should not be authenticated in session
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_verified_supplier_redirects_to_dashboard(self):
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
            verification_status='manual_approved'
        )

        response = self.client.post('/login/', {'username': 'verified_supplier', 'password': 'Password123#'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/dashboard/')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_verified_buyer_redirects_to_marketplace(self):
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
            verification_status='auto_verified'
        )

        response = self.client.post('/login/', {'username': 'verified_buyer', 'password': 'Password123#'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_admin_verification_hub_actions(self):
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
