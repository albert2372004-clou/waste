from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal

from accounts.models import Company
from marketplace.models import (
    MaterialCategory,
    MaterialListing,
    Certificate,
    ProcurementRequest,
    AggregationPool,
    FundingProject,
)


class Command(BaseCommand):
    help = "Populate the Circular Waste Intelligence Platform with Kerala Industrial Corridor data"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Anti Gravity: Kerala Circular Waste Intelligence Platform data..."))

        # 1. Categories
        categories_data = [
            {
                "name": "Scrap Rubber",
                "code": "rubber",
                "standard_price_per_ton": Decimal("20000.00"),
                "carbon_offset_factor": Decimal("1.69"),
                "description": "Shredded tyre crumbs, vulcanized offcuts, and reclaimed latex compound from Kerala plantation belts."
            },
            {
                "name": "Textile Remnants",
                "code": "textile",
                "standard_price_per_ton": Decimal("15000.00"),
                "carbon_offset_factor": Decimal("2.10"),
                "description": "Handloom and apparel cotton shreds, woven selvages, and knitted offcuts from Kannur & Kochi apparel hubs."
            },
            {
                "name": "Coconut Shells & Coir",
                "code": "coconut",
                "standard_price_per_ton": Decimal("12000.00"),
                "carbon_offset_factor": Decimal("1.45"),
                "description": "Crushed coconut shells, coir pith, and biomass char for activated carbon and agro-substrates from Alappuzha."
            },
            {
                "name": "Plastic Fragments",
                "code": "plastic",
                "standard_price_per_ton": Decimal("25000.00"),
                "carbon_offset_factor": Decimal("1.85"),
                "description": "Reground HDPE, washed PET flakes, and industrial packaging film trim from Palakkad plastics parks."
            },
            {
                "name": "Fish Scales & Marine Organics",
                "code": "fish",
                "standard_price_per_ton": Decimal("8500.00"),
                "carbon_offset_factor": Decimal("1.15"),
                "description": "Descaled marine byproduct rich in organic collagen precursors from Munambam & Cochin harbours."
            },
        ]

        categories = {}
        for cat in categories_data:
            c, _ = MaterialCategory.objects.update_or_create(
                code=cat["code"],
                defaults={
                    "name": cat["name"],
                    "standard_price_per_ton": cat["standard_price_per_ton"],
                    "carbon_offset_factor": cat["carbon_offset_factor"],
                    "description": cat["description"]
                }
            )
            categories[cat["code"]] = c

        self.stdout.write(self.style.SUCCESS(f"&check; Seeded {len(categories)} Material Categories."))

        def create_or_update_company(user, reg_num, gstin, defaults):
            comp = Company.objects.filter(registration_number=reg_num).first()
            if not comp:
                comp = Company.objects.filter(gstin=gstin).first()
            if not comp:
                comp = Company.objects.filter(user=user).first()
            if comp:
                comp.user = user
                for k, v in defaults.items():
                    setattr(comp, k, v)
                comp.registration_number = reg_num
                comp.gstin = gstin
                comp.save()
                return comp
            return Company.objects.create(user=user, registration_number=reg_num, gstin=gstin, **defaults)

        # 2. Users & Companies (Kerala Industrial Corridor)
        # Supplier 1: Kerala Rubber Reprocessors (Kottayam)
        u1, _ = User.objects.get_or_create(username="kerala_rubber", defaults={"email": "rubber@keralareclaim.com"})
        u1.set_password("Supplier123#")
        u1.save()
        c1 = create_or_update_company(
            u1, "REG-KL-2291", "32AABCK2291M1Z8",
            {
                "company_name": "Kerala Rubber Reprocessors Pvt. Ltd.",
                "authorized_person": "Mathew Varghese",
                "phone": "9846012345",
                "address": "Kottayam Rubber Industrial Park, Kottayam, Kerala",
                "user_type": "supplier",
                "verification_status": "auto_verified",
                "verified_at": timezone.now()
            }
        )

        # Supplier 2 / Dual Enterprise: Malabar Coir & Bio-Carbon (Alappuzha) - Both Buyer and Supplier!
        u2, _ = User.objects.get_or_create(username="malabar_coir", defaults={"email": "sales@malabarcoir.com"})
        u2.set_password("Supplier123#")
        u2.save()
        c2 = create_or_update_company(
            u2, "REG-KL-7119", "32AABCM7119M1Z3",
            {
                "company_name": "Malabar Coir & Bio-Carbon Ltd.",
                "authorized_person": "Anjali Pillai",
                "phone": "9847198765",
                "address": "Coir Industrial Zone, Alappuzha, Kerala",
                "user_type": "both",  # Dual role enterprise
                "verification_status": "manual_approved",
                "verified_at": timezone.now()
            }
        )

        # Supplier 3: Cochin Technical Polymers (Kochi)
        u3, _ = User.objects.get_or_create(username="cochin_polymers", defaults={"email": "info@cochinpolymers.com"})
        u3.set_password("Supplier123#")
        u3.save()
        c3 = create_or_update_company(
            u3, "REG-KL-4028", "32AABCC4028M1Z6",
            {
                "company_name": "Cochin Polymers & Technical Reclaimers",
                "authorized_person": "Faisal Rahman",
                "phone": "9846055223",
                "address": "Kochi Petrochemical Corridor, Willingdon Island, Kochi, Kerala",
                "user_type": "supplier",
                "verification_status": "auto_verified",
                "verified_at": timezone.now()
            }
        )

        # Buyer 1: Travancore Infrastructure & Highway Works (Palakkad Corridor)
        u_buyer, _ = User.objects.get_or_create(username="travancore_infra", defaults={"email": "procurement@travancoreinfra.com"})
        u_buyer.set_password("Buyer123#")
        u_buyer.save()
        c_buyer = create_or_update_company(
            u_buyer, "REG-KL-8821", "32AABCT8821M1Z9",
            {
                "company_name": "Travancore Infrastructure & Roadworks Corp.",
                "authorized_person": "Siddharth Menon",
                "phone": "9847055443",
                "address": "KINFRA Integrated Industrial Park, Kanjikode, Palakkad, Kerala",
                "user_type": "buyer",
                "verification_status": "auto_verified",
                "verified_at": timezone.now()
            }
        )

        # Also update demo admin
        admin_u, _ = User.objects.get_or_create(username="admin", defaults={"email": "admin@circularexchange.org", "is_staff": True, "is_superuser": True})
        admin_u.set_password("Admin123#")
        admin_u.save()

        self.stdout.write(self.style.SUCCESS("&check; Seeded Kerala Enterprise Companies & Users (including Dual Enterprise)."))

        # 3. Listings with Quality Grades, Sampling Protocols, and Kerala locations
        listings_data = [
            {
                "supplier": c1,
                "material_name": "Shredded Tyre Crumb Rubber (Grade A Asphalt Blend)",
                "category": "rubber",
                "batch_id": "KL-SR-2291",
                "price_per_ton": Decimal("19200.00"),
                "recommended_price": Decimal("19200.00"),
                "volume_tons": Decimal("380.00"),
                "purity_percent": 96,
                "quality_grade": "grade_a",
                "sampling_protocol": "ASTM D6323 Multi-point composite sampling guarantee across 380t",
                "trust_score": 98,
                "location": "Kottayam Rubber Complex, Kerala",
                "moq_tons": Decimal("20.00"),
                "lead_time_days": 4,
                "packaging_type": "Woven poly bulk bags, 500 kg",
                "moisture_percent": Decimal("1.80"),
                "contamination_percent": Decimal("0.40"),
                "particle_size": "2–5 mm granules",
                "compliance_id": "KSPCB-WM-22910",
                "status": "active"
            },
            {
                "supplier": c1,
                "material_name": "Reclaimed Latex & Vulcanized Offcuts",
                "category": "rubber",
                "batch_id": "KL-SR-2278",
                "price_per_ton": Decimal("16500.00"),
                "recommended_price": Decimal("16800.00"),
                "volume_tons": Decimal("140.00"),
                "purity_percent": 91,
                "quality_grade": "grade_b",
                "sampling_protocol": "Baled core extraction test per 10-bale lot",
                "trust_score": 94,
                "location": "Palakkad Bypass Yard, Kerala",
                "moq_tons": Decimal("15.00"),
                "lead_time_days": 5,
                "packaging_type": "Baled stacks on wooden pallets",
                "moisture_percent": Decimal("2.10"),
                "contamination_percent": Decimal("0.80"),
                "particle_size": "Solid strips (10-30 cm)",
                "compliance_id": "KSPCB-WM-22781",
                "status": "active"
            },
            {
                "supplier": c2,
                "material_name": "Crushed Coconut Shells (Grade A Activated Carbon Precursor)",
                "category": "coconut",
                "batch_id": "KL-CS-4028",
                "price_per_ton": Decimal("11800.00"),
                "recommended_price": Decimal("11800.00"),
                "volume_tons": Decimal("420.00"),
                "purity_percent": 98,
                "quality_grade": "grade_a",
                "sampling_protocol": "IS 2750 Standard cross-cone sampling for charcoal media",
                "trust_score": 99,
                "location": "Alappuzha Agro Complex, Kerala",
                "moq_tons": Decimal("25.00"),
                "lead_time_days": 4,
                "packaging_type": "PP Woven sacks, 50 kg",
                "moisture_percent": Decimal("3.20"),
                "contamination_percent": Decimal("0.20"),
                "particle_size": "5–12 mm uniform chips",
                "compliance_id": "KSPCB-WM-30044",
                "status": "active"
            },
            {
                "supplier": c3,
                "material_name": "Mixed PET & Industrial Polymer Flakes",
                "category": "plastic",
                "batch_id": "KL-PF-2260",
                "price_per_ton": Decimal("23500.00"),
                "recommended_price": Decimal("24000.00"),
                "volume_tons": Decimal("190.00"),
                "purity_percent": 88,
                "quality_grade": "grade_b",
                "sampling_protocol": "ASTM D5814 Flake color & polymer purity spectrometry",
                "trust_score": 91,
                "location": "Kochi Petrochemical Belt, Kerala",
                "moq_tons": Decimal("15.00"),
                "lead_time_days": 4,
                "packaging_type": "Gaylord corrugated bulk containers",
                "moisture_percent": Decimal("0.90"),
                "contamination_percent": Decimal("0.70"),
                "particle_size": "3–8 mm regrind",
                "compliance_id": "KSPCB-WM-55620",
                "status": "active"
            },
            {
                "supplier": c2,
                "material_name": "Kannur Handloom & Cotton Waste Remnants",
                "category": "textile",
                "batch_id": "KL-TR-7119",
                "price_per_ton": Decimal("14200.00"),
                "recommended_price": Decimal("14200.00"),
                "volume_tons": Decimal("260.00"),
                "purity_percent": 92,
                "quality_grade": "grade_b",
                "sampling_protocol": "Random bale core probe testing",
                "trust_score": 95,
                "location": "Kochi Free Trade Zone, Kerala",
                "moq_tons": Decimal("10.00"),
                "lead_time_days": 3,
                "packaging_type": "Compressed wire-tied bales, 200 kg",
                "moisture_percent": Decimal("1.20"),
                "contamination_percent": Decimal("0.30"),
                "particle_size": "Thread & fabric shreds",
                "compliance_id": "KSPCB-WM-29981",
                "status": "active"
            },
            {
                "supplier": c3,
                "material_name": "Marine Descaled Fish Waste (Collagen Precursor)",
                "category": "fish",
                "batch_id": "KL-FS-4011",
                "price_per_ton": Decimal("8200.00"),
                "recommended_price": Decimal("8200.00"),
                "volume_tons": Decimal("85.00"),
                "purity_percent": 95,
                "quality_grade": "grade_a",
                "sampling_protocol": "Food & Marine safety lab microbiological assay",
                "trust_score": 93,
                "location": "Munambam Harbour, Ernakulam, Kerala",
                "moq_tons": Decimal("10.00"),
                "lead_time_days": 2,
                "packaging_type": "Insulated refrigerated bulk totes",
                "moisture_percent": Decimal("6.50"),
                "contamination_percent": Decimal("0.10"),
                "particle_size": "Natural dried scales",
                "compliance_id": "KSPCB-WM-30102",
                "status": "active"
            }
        ]

        created_listings = []
        for l in listings_data:
            item, _ = MaterialListing.objects.update_or_create(
                batch_id=l["batch_id"],
                defaults={
                    "supplier": l["supplier"],
                    "material_name": l["material_name"],
                    "category": l["category"],
                    "category_ref": categories.get(l["category"]),
                    "price_per_ton": l["price_per_ton"],
                    "recommended_price": l["recommended_price"],
                    "volume_tons": l["volume_tons"],
                    "purity_percent": l["purity_percent"],
                    "quality_grade": l.get("quality_grade", "grade_a"),
                    "sampling_protocol": l.get("sampling_protocol", "ASTM D6323 Representative Composite Batch Sampling"),
                    "trust_score": l["trust_score"],
                    "location": l["location"],
                    "moq_tons": l["moq_tons"],
                    "lead_time_days": l["lead_time_days"],
                    "packaging_type": l["packaging_type"],
                    "moisture_percent": l["moisture_percent"],
                    "contamination_percent": l["contamination_percent"],
                    "particle_size": l["particle_size"],
                    "compliance_id": l["compliance_id"],
                    "description": l.get("description", f"High-grade industrial secondary raw stream sourced from {l['location']}."),
                    "quantity_unit": "Tons",
                    "condition": "Recyclable Clean",
                    "approval_status": "approved",
                    "status": l["status"],
                    "is_active": True,
                    "permit_verified": True
                }
            )
            created_listings.append(item)

        self.stdout.write(self.style.SUCCESS(f"&check; Seeded {len(created_listings)} Active Kerala Waste Streams."))

        # 4. Certificates
        Certificate.objects.update_or_create(
            supplier=c1,
            certificate_name="KSPCB Environmental Consent to Operate (CTO)",
            defaults={
                "certificate_type": "Pollution Board Consent",
                "material": "Crumb Rubber & Tyre Scrap",
                "issue_date": date.today() - timedelta(days=90),
                "expiry_date": date.today() + timedelta(days=275),
                "verification_status": "verified"
            }
        )
        Certificate.objects.update_or_create(
            supplier=c1,
            certificate_name="ISO 14001:2015 Environmental Management Standard",
            defaults={
                "certificate_type": "ISO Standards Certificate",
                "material": "All Plant Reclaimed Streams",
                "issue_date": date.today() - timedelta(days=180),
                "expiry_date": date.today() + timedelta(days=545),
                "verification_status": "verified"
            }
        )
        Certificate.objects.update_or_create(
            supplier=c2,
            certificate_name="BIS Carbon Assay & Purity Certification",
            defaults={
                "certificate_type": "Quality & Assay Certificate",
                "material": "Crushed Coconut Shells",
                "issue_date": date.today() - timedelta(days=45),
                "expiry_date": date.today() + timedelta(days=320),
                "verification_status": "verified"
            }
        )

        # 5. Aggregation Pools
        AggregationPool.objects.update_or_create(
            title="Crumb Rubber 500t Highway Project — Travancore Infra",
            defaults={
                "material_name": "Shredded Tyre Crumb Rubber",
                "buyer_name": "Travancore Infrastructure & Roadworks Corp.",
                "target_volume_tons": Decimal("500.00"),
                "collected_volume_tons": Decimal("380.00"),
                "contributing_suppliers_count": 2,
                "status": "filling"
            }
        )
        AggregationPool.objects.update_or_create(
            title="Activated Carbon Charcoal 400t Multi-Plant Aggregation",
            defaults={
                "material_name": "Crushed Coconut Shells",
                "buyer_name": "Kochi Activated Carbon Plant",
                "target_volume_tons": Decimal("400.00"),
                "collected_volume_tons": Decimal("400.00"),
                "contributing_suppliers_count": 3,
                "status": "fulfilled"
            }
        )

        # 6. Sample Live Order with Amazon/Flipkart-style Tracking
        l_first = created_listings[0]
        ProcurementRequest.objects.update_or_create(
            buyer=u_buyer,
            listing=l_first,
            defaults={
                "buyer_company": c_buyer,
                "volume_requested": Decimal("120.00"),
                "status": "accepted",
                "tracking_number": "AG-KL-72910",
                "delivery_status": "in_transit",
                "vehicle_number": "KL-07-BW-4921 (20t Closed Container Truck)",
                "driver_contact": "+91 98460 22100 (Kerala Freight Line)",
                "current_location": "NH 544 Aluva Bypass, En route to Palakkad Industrial Corridor",
                "eta_hours": "3.5 Hours",
                "tracking_progress_percent": 65,
                "origin_facility": "Kottayam Rubber Complex, Kottayam, Kerala",
                "destination_facility": "KINFRA Integrated Industrial Park, Kanjikode, Palakkad, Kerala",
                "transport_mode": "Closed Container Bulk Carrier (20t)",
                "estimated_distance_km": 142
            }
        )

        # 7. Circular Innovation & Micro-Funding Projects
        FundingProject.objects.update_or_create(
            title="Kottayam Micro-Crumb Rubber Cryogenic Processing Unit",
            defaults={
                "company": c1,
                "category": "rubber",
                "description": "Upgrading local mechanical shredding lines to liquid nitrogen cryogenic milling to produce ultra-fine 80 mesh rubber powder for asphalt modification.",
                "target_amount": Decimal("500000.00"),
                "raised_amount": Decimal("365000.00"),
                "status": "active"
            }
        )
        FundingProject.objects.update_or_create(
            title="Alappuzha Zero-Emission Coconut Husk Biochar Kiln",
            defaults={
                "company": c2,
                "category": "coconut",
                "description": "Installing closed-retort pyrolyzers capturing syngas emissions during coconut shell carbonization, creating agricultural biochar for soil carbon sequestration.",
                "target_amount": Decimal("350000.00"),
                "raised_amount": Decimal("280000.00"),
                "status": "active"
            }
        )
        FundingProject.objects.update_or_create(
            title="Munambam Fishery Waste Collagen Peptide Pilot Lab",
            defaults={
                "company": c3,
                "category": "fish",
                "description": "Setting up an enzymatic extraction laboratory converting discarded fish scales and skin into pharmaceutical and cosmetic grade bioactive collagen peptides.",
                "target_amount": Decimal("600000.00"),
                "raised_amount": Decimal("450000.00"),
                "status": "active"
            }
        )

        self.stdout.write(self.style.SUCCESS("All Kerala Industrial Corridor demonstration data successfully seeded!"))
