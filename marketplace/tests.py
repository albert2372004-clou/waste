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

    def test_category_name_conflict_fails_validation(self):
        """Listing fails validation if material title explicitly contradicts the selected category."""
        from marketplace.forms import MaterialListingForm
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Title conflict: Category 'rubber' but name mentions 'Fish'
        fake_img = SimpleUploadedFile("sample.jpg", b"\xff\xd8\xff\xe0dummy", content_type="image/jpeg")
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

    def test_image_verifier_matching_high_score(self):
        """Matching image content gives score >= 80% and 'Likely Match' status."""
        import io
        from PIL import Image
        import numpy as np
        from marketplace.services.image_verifier import verify_waste_image

        # Create genuine brown textured coconut shell image
        arr = np.full((128, 128, 3), (140, 90, 45), dtype=np.uint8)
        arr[:64, :64] = (160, 110, 55)
        arr[64:, 64:] = (110, 70, 35)
        img = Image.fromarray(arr)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)

        result = verify_waste_image(buf, "coconut")
        self.assertGreaterEqual(result["score"], 80.0)
        self.assertEqual(result["status"], "Likely Match")
        self.assertTrue(result["is_likely_match"])

    def test_image_verifier_mismatched_low_score(self):
        """Mismatched image content gives score < 50% and 'Possible Mismatch' status."""
        import io
        from PIL import Image
        from marketplace.services.image_verifier import verify_waste_image

        # Dark black tyre crumb image tested against coconut shell category
        img = Image.new("RGB", (128, 128), color=(25, 25, 28))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)

        result = verify_waste_image(buf, "coconut")
        self.assertLess(result["score"], 50.0)
        self.assertEqual(result["status"], "Possible Mismatch")
        self.assertTrue(result["is_mismatch"])
        self.assertEqual(result["detected_category"], "Scrap Rubber")

    def test_supplier_submission_never_blocked_by_image_mismatch(self):
        """Supplier must ALWAYS be able to submit a listing even if image is a mismatch."""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from marketplace.forms import MaterialListingForm

        # Create black rubber image
        img = Image.new("RGB", (128, 128), color=(20, 20, 22))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        uploaded_img = SimpleUploadedFile("IMG_48392.jpg", buf.getvalue(), content_type="image/jpeg")

        # Category selected is Coconut Shells, but image content is black rubber
        form = MaterialListingForm(
            data={
                "material_name": "Dry Coconut Shells Batch A",
                "category": "coconut",
                "volume_tons": 50.0,
                "quantity_unit": "Tons",
                "condition": "Recyclable Clean",
                "purity_percent": 90,
                "moisture_percent": 8.0,
                "contamination_percent": 2.0,
                "price_per_ton": 14000.00,
                "location": "Alappuzha, Kerala",
                "moq_tons": 10.0,
                "quality_grade": "grade_a",
                "sampling_protocol": "Standard Composite Sampling ASTM D6323",
                "lead_time_days": 4,
                "packaging_type": "Woven poly bulk bags, 500 kg",
                "particle_size": "2–5 mm",
                "compliance_id": "KPCB-WM-22910",
            },
            files={"image": uploaded_img}
        )
        # Form MUST be valid and NOT blocked!
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        # Save listing and verify status is recorded as Possible Mismatch
        listing = form.save(commit=False)
        listing.supplier = self.supplier_company
        listing.save()

        self.assertEqual(listing.image_verification_status, "Possible Mismatch")
        self.assertLess(listing.image_verification_score, 50.0)
        self.assertEqual(listing.image_detected_category, "Scrap Rubber")
        self.assertEqual(listing.category, "coconut")

    def test_invalid_corrupted_image_handling_safely(self):
        """Corrupted or invalid image files are handled safely without crashing."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from marketplace.services.image_verifier import verify_waste_image

        corrupted = SimpleUploadedFile("corrupted.jpg", b"This is not a real JPEG file", content_type="image/jpeg")
        result = verify_waste_image(corrupted, "rubber")

        self.assertEqual(result["status"], "Manual Review")
        self.assertEqual(result["score"], 0.0)
        self.assertIn("Corrupted", result["detected_category"])

    def test_multi_image_partial_match_keeps_matching_and_removes_mismatches(self):
        """When image 1 is correct and images 2 & 3 do not match, only include 1 and remove the other 2."""
        import io
        from PIL import Image
        import numpy as np
        from marketplace.services.image_verifier import process_multi_image_verification

        # Image 1: Valid Coconut Shell (brown fibrous)
        arr = np.full((128, 128, 3), (140, 90, 45), dtype=np.uint8)
        arr[:64, :64] = (160, 110, 55)
        arr[64:, 64:] = (110, 70, 35)
        img1 = Image.fromarray(arr)
        buf1 = io.BytesIO()
        img1.save(buf1, format="JPEG")
        buf1.seek(0)

        # Image 2: Black Rubber (Mismatch for coconut)
        img2 = Image.new("RGB", (128, 128), color=(25, 25, 28))
        buf2 = io.BytesIO()
        img2.save(buf2, format="JPEG")
        buf2.seek(0)

        # Image 3: Black Rubber (Mismatch for coconut)
        img3 = Image.new("RGB", (128, 128), color=(30, 30, 33))
        buf3 = io.BytesIO()
        img3.save(buf3, format="JPEG")
        buf3.seek(0)

        res = process_multi_image_verification(buf1, [buf2, buf3], "coconut")

        self.assertEqual(res["matched_count"], 1)
        self.assertEqual(res["mismatched_count"], 2)
        self.assertFalse(res["use_category_symbol"])
        # The 2 mismatched images were automatically removed from the gallery!
        self.assertEqual(len(res["verified_gallery"]), 0)
        self.assertIn("1 authentic image(s) verified", res["message"])
        self.assertIn("2 mismatched image(s) were automatically filtered out", res["message"])

    def test_multi_image_all_mismatch_automatically_applies_category_symbols(self):
        """When none of 1st, 2nd, or 3rd images match, automatically apply category symbols."""
        import io
        from PIL import Image
        from marketplace.services.image_verifier import process_multi_image_verification

        # 3 Dark Rubber images tested against Coconut category
        bufs = []
        for c in [(20, 20, 22), (25, 25, 28), (18, 18, 20)]:
            img = Image.new("RGB", (128, 128), color=c)
            b = io.BytesIO()
            img.save(b, format="JPEG")
            b.seek(0)
            bufs.append(b)

        res = process_multi_image_verification(bufs[0], bufs[1:], "coconut")

        self.assertEqual(res["matched_count"], 0)
        self.assertEqual(res["mismatched_count"], 3)
        self.assertTrue(res["use_category_symbol"])
        self.assertEqual(res["status"], "Possible Mismatch")
        self.assertEqual(len(res["verified_gallery"]), 0)
        self.assertIn("official industrial stream symbol has been automatically applied", res["message"])

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

    def test_standard_cart_mixed_categories(self):
        """Standard shopping cart allows adding multiple items from different categories."""
        from marketplace.services.aggregation import StandardCartService
        session = self.client.session
        cart = StandardCartService(session)

        # Listing 1 is rubber
        cart.add_item(self.listing, 25.0)

        # Create plastic listing
        cat_plastic = MaterialCategory.objects.create(
            name="Industrial Plastics",
            code="plastic",
            standard_price_per_ton=Decimal("25000.00"),
            carbon_offset_factor=Decimal("2.10")
        )
        plastic_listing = MaterialListing.objects.create(
            supplier=self.supplier_company,
            material_name="HDPE Shredded Regrind",
            category="plastic",
            price_per_ton=Decimal("24000.00"),
            volume_tons=Decimal("100.00"),
            moq_tons=Decimal("5.00"),
            location="Palakkad, Kerala",
            approval_status="approved",
            is_active=True,
        )

        # Adding plastic listing to standard cart succeeds (no category isolation conflict)
        cart.add_item(plastic_listing, 15.0)
        summary = cart.get_summary()

        self.assertEqual(summary["items_count"], 2)
        self.assertEqual(summary["total_tons"], 40.0)
        self.assertGreater(summary["grand_total"], 0)

    def test_batch_cart_excess_capping_never_exceeds_target(self):
        """Multi-factor aggregation detects excess from last supplier and caps to target."""
        session = self.client.session
        cart = BatchCartService(session)
        cart.set_target(50.0, "Scrap Rubber", "rubber")

        # Listing 1 adds 30 tons
        cart.add_listing(self.listing, 30.0)
        summary1 = cart.get_summary()
        self.assertEqual(summary1["collected_tons"], 30.0)
        self.assertEqual(summary1["remaining_tons"], 20.0)

        # Second rubber supplier listing with 40 tons
        listing2 = MaterialListing.objects.create(
            supplier=self.supplier_company,
            material_name="Vulcanized Rubber Granules",
            category="rubber",
            price_per_ton=Decimal("19000.00"),
            volume_tons=Decimal("40.00"),
            moq_tons=Decimal("10.00"),
            location="Kochi, Kerala",
            approval_status="approved",
            is_active=True,
        )

        # Add 40 tons: since only 20 tons is needed, it must be capped to 20 tons!
        cart.add_listing(listing2, 40.0, cap_to_target=True)
        summary2 = cart.get_summary()

        self.assertEqual(summary2["collected_tons"], 50.0)
        self.assertEqual(summary2["remaining_tons"], 0.0)
        self.assertTrue(summary2["is_fully_filled"])

    def test_cart_add_respects_custom_buyer_quantity(self):
        """When buyer increases quantity beyond MOQ, cart_add receives and records that quantity."""
        self.client.force_login(self.buyer_user)
        # MOQ is 10 tons, buyer requests 75 tons
        response = self.client.post(f"/cart/add/{self.listing.pk}/", {"volume_requested": "75.0"})
        self.assertEqual(response.status_code, 302)

        session = self.client.session
        cart = BatchCartService(session)
        summary = cart.get_summary()

        # Target should have accommodated 75 tons, and collected should be 75 tons (not 10 tons!)
        self.assertEqual(summary["collected_tons"], 75.0)


