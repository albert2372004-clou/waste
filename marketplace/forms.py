from django import forms
from .models import (
    MaterialListing,
    Certificate,
    ProcurementRequest,
    MaterialCategory,
    ListingImage,
    ReportedListing,
    FundingProject
)
from .services.pricing import get_standard_rate
from .services.consistency import check_material_consistency
import os


class MaterialListingForm(forms.ModelForm):
    image = forms.FileField(
        required=True,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        help_text="Compulsory: Upload high-resolution batch photo (.jpg, .png, .webp)"
    )

    class Meta:
        model = MaterialListing
        fields = [
            'material_name',
            'category',
            'description',
            'price_per_ton',
            'volume_tons',
            'quantity_unit',
            'condition',
            'purity_percent',
            'quality_grade',
            'lab_accreditation_number',
            'image',
            'quality_certificate',
            'sampling_protocol',
            'location',
            'moq_tons',
            'lead_time_days',
            'packaging_type',
            'moisture_percent',
            'contamination_percent',
            'particle_size',
            'compliance_id',
        ]
        widgets = {
            'material_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Shredded Tyre Crumb Rubber (Grade A)'}),
            'category': forms.Select(attrs={'class': 'form-control', 'id': 'id_category'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe byproduct origin, composition, storage condition, and recommended applications'}),
            'price_per_ton': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_price_per_ton', 'step': '0.01'}),
            'volume_tons': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_volume_tons', 'step': '0.1'}),
            'quantity_unit': forms.Select(attrs={'class': 'form-control'}),
            'condition': forms.Select(attrs={'class': 'form-control'}),
            'purity_percent': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_purity_percent', 'min': '50', 'max': '100'}),
            'quality_grade': forms.Select(attrs={'class': 'form-control', 'id': 'id_quality_grade'}),
            'lab_accreditation_number': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_lab_accreditation', 'placeholder': 'e.g. NABL-KL-2026/TC-8812 or ISO 17025 ID'}),
            'sampling_protocol': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_sampling_protocol'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Kochi Industrial Corridor, Kerala'}),
            'moq_tons': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'lead_time_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'packaging_type': forms.TextInput(attrs={'class': 'form-control'}),
            'moisture_percent': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_moisture_percent', 'step': '0.1'}),
            'contamination_percent': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_contamination_percent', 'step': '0.1'}),
            'particle_size': forms.TextInput(attrs={'class': 'form-control'}),
            'compliance_id': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_image(self):
        img = self.cleaned_data.get('image')
        if img:
            ext = os.path.splitext(img.name)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
                raise forms.ValidationError('Image must be a valid image file (.jpg, .jpeg, .png, .webp).')
            if img.size > 8 * 1024 * 1024:
                raise forms.ValidationError('Image size must not exceed 8MB.')
        return img

    def clean_quality_certificate(self):
        doc = self.cleaned_data.get('quality_certificate')
        if doc:
            ext = os.path.splitext(doc.name)[1].lower()
            if ext not in ['.pdf', '.png', '.jpg', '.jpeg']:
                raise forms.ValidationError('Lab test sheet must be in PDF or Image format (.pdf, .png, .jpg, .jpeg).')
            if doc.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Quality certificate file must not exceed 10MB.')
        return doc

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get('price_per_ton')
        volume = cleaned_data.get('volume_tons')
        moq = cleaned_data.get('moq_tons')
        purity = cleaned_data.get('purity_percent')
        moisture = cleaned_data.get('moisture_percent')
        contamination = cleaned_data.get('contamination_percent')
        category = cleaned_data.get('category')

        # 1. Price Sanity Check against Standard Benchmark
        if price is not None and price <= 0:
            self.add_error('price_per_ton', 'Price per ton must be a positive value.')

        if category and price is not None:
            std_rate = float(get_standard_rate(category))
            if float(price) > std_rate * 3.0:
                self.add_error(
                    'price_per_ton',
                    f"Warning: Offering rate (₹{price}) is over 3x the standard benchmark for {category} (₹{std_rate:.0f}). Please verify entered value."
                )

        # 2. Volume vs MOQ Sanity Check
        if volume is not None and volume <= 0:
            self.add_error('volume_tons', 'Available batch volume must be greater than 0 tons.')

        if volume is not None and moq is not None and volume < moq:
            self.add_error('volume_tons', f'Available volume ({volume}t) cannot be smaller than Minimum Order Quantity (MOQ: {moq}t).')

        # 3. Purity & Impurity Physical Logic Sanity Check
        if purity is not None:
            if purity < 1 or purity > 100:
                self.add_error('purity_percent', 'Purity rating must be between 1% and 100%.')

        if moisture is not None and (moisture < 0 or moisture > 100):
            self.add_error('moisture_percent', 'Moisture percentage must be between 0% and 100%.')

        if contamination is not None and (contamination < 0 or contamination > 100):
            self.add_error('contamination_percent', 'Contamination level must be between 0% and 100%.')

        # Physical balance: Purity + Moisture + Contamination cannot exceed 100%
        if purity and moisture and contamination:
            if float(purity) + float(moisture) + float(contamination) > 105.0:  # 5% tolerance for lab variance
                self.add_error(
                    'contamination_percent',
                    f'Physical measurement balance error: Purity ({purity}%) + Moisture ({moisture}%) + Contamination ({contamination}%) exceeds 100%!'
                )

        # 4. Strict Category-Specific Waste Stream Threshold Invariants
        if category:
            if category == 'rubber':
                if moisture is not None and float(moisture) > 8.0:
                    self.add_error('moisture_percent', 'Rubber moisture exceeds 8% standard tolerance. High moisture degrades asphalt polymer blending.')
                if purity is not None and float(purity) < 70.0:
                    self.add_error('purity_percent', 'Scrap rubber purity below 70% is classified as unsorted hazardous residue and cannot be traded.')
            elif category == 'textile':
                if contamination is not None and float(contamination) > 12.0:
                    self.add_error('contamination_percent', 'Textile shreds contamination exceeds 12%. Synthetic foreign matter prevents acoustic batt production.')
            elif category == 'coconut':
                if moisture is not None and float(moisture) > 15.0:
                    self.add_error('moisture_percent', 'Coconut shell moisture exceeds 15%. Biomass char requires dry feedstock for activated carbon kilns.')
            elif category == 'plastic':
                if contamination is not None and float(contamination) > 5.0:
                    self.add_error('contamination_percent', 'Plastic flake contamination exceeds 5%. Industrial extruder recyclers require max 5% impurities.')
            elif category == 'fish':
                if moisture is not None and float(moisture) > 20.0:
                    self.add_error('moisture_percent', 'Marine fish scales moisture exceeds 20%. Descaled byproduct must be solar/kiln dried before transit.')

        # 5. Consistency Checking & Preliminary Computer Vision Image Verification
        mat_name = cleaned_data.get('material_name', '')
        img_obj = cleaned_data.get('image')
        cert_obj = cleaned_data.get('quality_certificate')
        cert_fname = cert_obj.name if cert_obj else ""

        if category and mat_name:
            consistency = check_material_consistency(category, mat_name, "")
            if not consistency['is_consistent']:
                if consistency['name_conflict']:
                    self.add_error(
                        'material_name',
                        f"Category Conflict: Material title references '{consistency['name_conflict']}' which does not match selected stream '{category.capitalize()}'. Listing blocked."
                    )

        # Content-based preliminary image verification (Never blocks listing submission)
        if img_obj and category:
            from .services.image_verifier import verify_waste_image
            v_res = verify_waste_image(img_obj, category)
            self.image_verification_result = v_res
            if v_res.get('is_mismatch'):
                cleaned_data['mismatch_warning'] = v_res['message']

        # 6. Quality Certificate Lab Assay vs Declared Purity Validation
        if cert_obj and purity is not None:
            from .services.extractor import extract_certificate_data
            cert_data = extract_certificate_data(file_obj=cert_obj, filename=cert_fname)
            cert_purity = cert_data.get('suggested_purity')
            if cert_purity and purity > (cert_purity + 5):
                self.add_error(
                    'purity_percent',
                    f"Purity Conflict: Declared purity ({purity}%) contradicts the lab certificate assay ({cert_purity}%). Supplier cannot submit unverified purity. Please auto-fill from certificate or correct declared rating."
                )
            if cert_fname:
                cert_check = check_material_consistency(category, "", cert_fname)
                if not cert_check['is_consistent'] and cert_check['image_conflict']:
                    self.add_error(
                        'quality_certificate',
                        f"Certificate Conflict: Uploaded lab document '{cert_fname}' indicates '{cert_check['image_conflict']}' which does not match selected stream '{category.capitalize()}'."
                    )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if hasattr(self, 'image_verification_result') and self.image_verification_result:
            instance.image_verification_status = self.image_verification_result['status']
            instance.image_verification_score = self.image_verification_result['score']
            instance.image_detected_category = self.image_verification_result['detected_category']
            instance.use_category_symbol = self.image_verification_result.get('is_mismatch', False)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ReportedListingForm(forms.ModelForm):
    class Meta:
        model = ReportedListing
        fields = ['reason', 'details']
        widgets = {
            'reason': forms.Select(
                choices=[
                    ('Misleading / Incorrect Category', 'Misleading / Incorrect Category'),
                    ('Suspected Fake Image / Quality Sheet', 'Suspected Fake Image / Quality Sheet'),
                    ('Mismatched Chemical Assay Purity', 'Mismatched Chemical Assay Purity'),
                    ('Commercial Non-compliance / Scam', 'Commercial Non-compliance / Scam'),
                    ('Other', 'Other Violation'),
                ],
                attrs={'class': 'form-control'}
            ),
            'details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Provide specific details for admin investigation...'}),
        }


class FundingPledgeForm(forms.Form):
    pledge_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=1000.00,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 50000.00'})
    )
    investor_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company or Representative Name'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Proposed partnership terms or circular grant notes...'})
    )


class CertificateForm(forms.ModelForm):
    class Meta:
        model = Certificate
        fields = [
            'certificate_name',
            'certificate_type',
            'material',
            'issue_date',
            'expiry_date',
            'document',
        ]
        widgets = {
            'certificate_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Kerala SPCB Consent to Operate (CTO)'}),
            'certificate_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Environmental Permit / ISO 14001 / Lab Test'}),
            'material': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Scrap Rubber Crumb'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'document': forms.FileInput(attrs={'class': 'form-control'}),
        }


class StandardRateConfigForm(forms.ModelForm):
    class Meta:
        model = MaterialCategory
        fields = ['standard_price_per_ton', 'carbon_offset_factor', 'description']
        widgets = {
            'standard_price_per_ton': forms.NumberInput(attrs={'class': 'form-control', 'step': '100.00'}),
            'carbon_offset_factor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
