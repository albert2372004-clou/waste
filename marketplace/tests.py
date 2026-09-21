from django.test import TestCase, Client
from django.contrib.auth.models import User
from decimal import Decimal

from accounts.models import Company
from marketplace.models import (
    MaterialCategory,
    MaterialListing,
    ProcurementRequest,
    AggregationPool,
)
from marketplace.services.pricing import calculate_recommended_rate
from marketplace.services.matching import calculate_match_score
from marketplace.services.carbon import calculate_carbon_savings
from marketplace.services.aggregation import BatchCartService


class MarketplaceCoreEngineTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Category
        self.category = MaterialCategory.objects.create(
            name="Scrap Rubber",
            code="rubber",
            standard_price_per_ton=Decimal("20000.00"),
            carbon_offset_factor=Decimal("1.69")
        )

        # Create Supplier
        self.supplier_user = User.objects.create_user(username="test_supplier", password="Password123#")
        self.supplier_company = Company.objects.create(
            user=self.supplier_user,
            company_name="Test Rubber Corp",
            registration_number="REG-SUPP-01",
            gstin="32AABCT0001M1Z5",
            authorized_person="Mr. Supplier",
            phone="9846000001",
            address="Kottayam Industrial Area, Kerala",
            user_type="supplier",
            verification_status="auto_verified"
        )

        # Create Buyer
        self.buyer_user = User.objects.create_user(username="test_buyer", password="Password123#")
        self.buyer_company = Company.objects.create(
            user=self.buyer_user,
            company_name="Test Buyer Infrastructure",
            registration_number="REG-BUYR-01",
            gstin="32AABCB0001M1Z9",
            authorized_person="Ms. Buyer",
            phone="9846000002",
            address="KINFRA Park, Palakkad, Kerala",
            user_type="buyer",
            verification_status="auto_verified"
        )

        # Create Material Listing
        self.listing = MaterialListing.objects.create(
            supplier=self.supplier_company,
            material_name="Industrial Tyre Crumb Rubber",
            category="rubber",
            category_ref=self.category,
            price_per_ton=Decimal("19000.00"),
            recommended_price=Decimal("18500.00"),
            volume_tons=Decimal("300.00"),
            purity_percent=92,
            trust_score=95,
            location="Kottayam, Kerala",
            approval_status="approved",
            is_active=True
        )

    def test_price_recommendation_formula(self):
        # Base: 20000, Purity: 90%, Volume: 200t (vol_factor 1.04) -> 20000 * 0.90 * 1.04 = 18720.00
        rec_price = calculate_recommended_rate("rubber", 90, 200)
        self.assertEqual(rec_price, Decimal("18720.00"))

    def test_rule_based_matching_engine(self):
        match = calculate_match_score(self.listing, target_category="rubber", min_purity=90)
        self.assertTrue(match["eligible"])
        self.assertGreaterEqual(match["score_percent"], 70)

        # Mismatched category should return 0% match
        mismatch = calculate_match_score(self.listing, target_category="plastic")
        self.assertEqual(mismatch["score_percent"], 0)

    def test_carbon_savings_calculation(self):
        res = calculate_carbon_savings(100.0, "rubber")
        self.assertEqual(res["co2e_tons"], 169.0)

    def test_multi_supplier_batch_cart_aggregation(self):
        # Initialize session-based cart
        session = self.client.session
        cart = BatchCartService(session)
        cart.set_target(1000.0, "Scrap Rubber")

        # Add 300 tons
        cart.add_listing(self.listing, 300.0)
        summary = cart.get_summary()

        self.assertEqual(summary["target_tons"], 1000.0)
        self.assertEqual(summary["collected_tons"], 300.0)
        self.assertEqual(summary["remaining_tons"], 700.0)
        self.assertEqual(summary["progress_pct"], 30)

        # Add 700 tons
        cart.add_listing(self.listing, 700.0)
        summary_full = cart.get_summary()
        self.assertEqual(summary_full["collected_tons"], 700.0)

    def test_procurement_request_workflow(self):
        self.client.force_login(self.buyer_user)
        # Buyer places order
        response = self.client.post(f"/checkout/{self.listing.pk}/", {"volume_requested": "50.00"})
        self.assertEqual(response.status_code, 302)

        req = ProcurementRequest.objects.filter(buyer=self.buyer_user, listing=self.listing).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.status, "pending")
        self.assertEqual(req.payment_status, "escrow_held")
        self.assertEqual(req.volume_requested, Decimal("50.00"))

        # Initial listing volume was 300 tons
        self.assertEqual(self.listing.volume_tons, Decimal("300.00"))

        # Supplier accepts request
        self.client.force_login(self.supplier_user)
        r_accept = self.client.post(f"/supplier/requests/{req.pk}/respond/", {"action": "accept"})
        self.assertEqual(r_accept.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, "accepted")
        self.assertEqual(req.payment_status, "released_to_supplier")
        self.assertEqual(req.delivery_status, "in_transit")

        # Verify waste inventory was reduced by 50 tons
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.volume_tons, Decimal("250.00"))

    def test_public_unregistered_visitor_can_browse_marketplace(self):
        """Unregistered public visitors can view all active listings in Kerala corridor without login."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.listing.material_name)
        self.assertContains(response, "Kerala Industrial Corridor")

    def test_dual_role_enterprise_permissions(self):
        """Enterprises registered as 'both' can act as both Buyer and Supplier."""
        u_dual = User.objects.create_user(username="dual_enterprise", password="Password123#")
        c_dual = Company.objects.create(
            user=u_dual,
            company_name="Kerala Circular Hub Pvt Ltd",
            registration_number="REG-DUAL-01",
            gstin="32AABCD0001M1Z5",
            authorized_person="Dr. Nair",
            phone="9846000003",
            address="Aluva Industrial Belt, Kerala",
            user_type="both",
            verification_status="auto_verified"
        )
        self.assertTrue(c_dual.can_sell)
        self.assertTrue(c_dual.can_buy)

    def test_freight_and_corridor_tracking_calculation(self):
        """Tests base dispatch + distance-based ton-km freight formula."""
        req = ProcurementRequest.objects.create(
            buyer=self.buyer_user,
            buyer_company=self.buyer_company,
            listing=self.listing,
            volume_requested=Decimal("20.00"),
            estimated_distance_km=142,
            origin_facility="Kochi, Kerala",
            destination_facility="Palakkad, Kerala",
        )
        # Base: 1500.00 + Toll: 450.00 + Freight: 20 * 142 * 3.20 = 9088.00 -> 11038.00
        self.assertEqual(req.estimated_freight(), 11038.00)
        # Material subtotal: 20 * 19000 = 380,000.00
        self.assertEqual(req.subtotal(), Decimal("380000.00"))
        self.assertEqual(req.total_cost(), 391038.00)
        self.assertTrue(req.tracking_number.startswith("AG-KL-"))

    def test_listing_form_physical_balance_validation(self):
        """Purity + Moisture + Contamination cannot exceed 100%."""
        from marketplace.forms import MaterialListingForm
        form = MaterialListingForm(data={
            "material_name": "Invalid Balance Byproduct",
            "category": "rubber",
            "volume_tons": 50.0,
            "purity_percent": 90,
            "price_per_ton": 18000.00,
            "moisture_percent": 15.0,  # 90 + 15 + 5 = 110% > 100%!
            "contamination_percent": 5.0,
            "location": "Kochi, Kerala",
            "moq_tons": 10.0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Physical measurement balance error", form.errors.get("contamination_percent", [""])[0])

    def test_category_specific_waste_threshold_validation(self):
        """Scrap rubber with moisture > 8% must be rejected."""
        from marketplace.forms import MaterialListingForm
        form = MaterialListingForm(data={
            "material_name": "Wet Scrap Rubber",
            "category": "rubber",
            "volume_tons": 50.0,
            "purity_percent": 88,
            "price_per_ton": 18000.00,
            "moisture_percent": 9.5,  # > 8% max tolerance!
            "contamination_percent": 1.0,
            "location": "Kottayam, Kerala",
            "moq_tons": 10.0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Rubber moisture exceeds 8%", form.errors.get("moisture_percent", [""])[0])

    def test_unapproved_listing_hidden_from_public_catalog(self):
        """Unapproved listings (pending/rejected) must NOT be visible on public index."""
        pending_listing = MaterialListing.objects.create(
            supplier=self.supplier_company,
            material_name="Secret Unapproved Scrap",
            category="rubber",
            category_ref=self.category,
            price_per_ton=Decimal("15000.00"),
            volume_tons=Decimal("50.00"),
            purity_percent=85,
            approval_status="pending",
            is_active=True
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Secret Unapproved Scrap")
        self.assertContains(response, self.listing.material_name)

    def test_certificate_extraction_api(self):
        """POSTing a certificate file to /api/extract-cert/ returns structured suggestions."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_cert = SimpleUploadedFile("nabl_test_report.pdf", b"%PDF-1.4 test report", content_type="application/pdf")
        response = self.client.post("/api/extract-cert/", {"certificate": fake_cert})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("suggested_purity", data["data"])
        self.assertIn("suggested_grade", data["data"])

    def test_reporting_listing(self):
        """Authenticated users can report suspicious or inaccurate listings."""
        from marketplace.models import ReportedListing
        self.client.force_login(self.buyer_user)
        response = self.client.post(f"/report/{self.listing.pk}/", {
            "reason": "Suspected Fake Image / Quality Sheet",
            "details": "The photo appears to be of HDPE flakes rather than rubber crumb."
        })
        self.assertEqual(response.status_code, 302)
        report = ReportedListing.objects.filter(listing=self.listing).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.reported_by, self.buyer_user)
        self.assertFalse(report.is_resolved)

    def test_circular_funding_pledge(self):
        """Users can pledge funds to circular projects."""
        from marketplace.models import FundingProject
        project = FundingProject.objects.create(
            company=self.supplier_company,
            title="Kottayam Cryogenic Milling Test",
            category="rubber",
            description="Cryogenic milling test setup",
            target_amount=Decimal("100000.00"),
            raised_amount=Decimal("20000.00"),
            status="active"
        )
        self.client.force_login(self.buyer_user)
        response = self.client.post(f"/funding/{project.pk}/pledge/", {"amount": "5000"})
        self.assertEqual(response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.raised_amount, Decimal("25000.00"))

    def test_supplier_button_visibility_restrictions(self):
        """Pure suppliers must NOT see buyer procurement buttons or requisition form."""
        self.client.force_login(self.supplier_user)

        # 1. Product Detail Page
        response = self.client.get(f"/product/{self.listing.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supplier View Mode")
        self.assertNotContains(response, "Send Direct Procurement Request")
        self.assertNotContains(response, "+ Add to Multi-Supplier Batch Cart")

        # 2. Marketplace Catalog Page
        index_resp = self.client.get("/")
        self.assertEqual(index_resp.status_code, 200)
        # Should not have '+ Cart' button on listing card for supplier
        self.assertNotContains(index_resp, "title=\"Add to Multi-Supplier Cart\"")

    def test_category_name_and_image_mismatch_fails_validation(self):
        """Listing fails validation if material name or image contradicts the selected category."""
        from marketplace.forms import MaterialListingForm
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Title conflict: Category 'rubber' but name mentions 'Fish'
        fake_img = SimpleUploadedFile("tyre_crumb.jpg", b"dummy image data", content_type="image/jpeg")
        form_bad_name = MaterialListingForm(
            data={
                "material_name": "Marine Fish Scales Residue",
                "category": "rubber",
                "volume_tons": 50.0,
                "purity_percent": 90,
                "price_per_ton": 18000.00,
                "location": "Kottayam, Kerala",
                "moq_tons": 10.0,
            },
            files={"image": fake_img}
        )
        self.assertFalse(form_bad_name.is_valid())
        self.assertIn("Category Conflict", form_bad_name.errors.get("material_name", [""])[0])

        # Image conflict: Category 'rubber' but image filename is 'fish_scales.jpg'
        bad_img = SimpleUploadedFile("fish_scales.jpg", b"dummy image data", content_type="image/jpeg")
        form_bad_img = MaterialListingForm(
            data={
                "material_name": "Shredded Tyre Crumb Rubber",
                "category": "rubber",
                "volume_tons": 50.0,
                "purity_percent": 90,
                "price_per_ton": 18000.00,
                "location": "Kottayam, Kerala",
                "moq_tons": 10.0,
            },
            files={"image": bad_img}
        )
        self.assertFalse(form_bad_img.is_valid())
        self.assertIn("Image Conflict", form_bad_img.errors.get("image", [""])[0])

    def test_purity_conflict_fails_validation(self):
        """Declared purity exceeding certificate assay by >5% must fail validation."""
        from marketplace.forms import MaterialListingForm
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Certificate for rubber yields suggested purity 95%. Declaring 101% or 100% when assay is 90%
        # Let's use a generic certificate (assay 91.5% -> suggested 91). Declaring 98% > 91 + 5 = 96%
        cert = SimpleUploadedFile("generic_assay_report.pdf", b"%PDF-1.4 test report", content_type="application/pdf")
        img = SimpleUploadedFile("crumb_rubber.jpg", b"image data", content_type="image/jpeg")
        form = MaterialListingForm(
            data={
                "material_name": "Shredded Tyre Crumb Rubber",
                "category": "rubber",
                "volume_tons": 50.0,
                "purity_percent": 99,  # 99% > 91 + 5 = 96%
                "price_per_ton": 18000.00,
                "location": "Kottayam, Kerala",
                "moq_tons": 10.0,
            },
            files={"image": img, "quality_certificate": cert}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Purity Conflict", form.errors.get("purity_percent", [""])[0])

