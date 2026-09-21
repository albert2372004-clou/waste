from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import Company


class CompanySignupForm(forms.Form):

    username = forms.CharField(
        max_length=150
    )

    email = forms.EmailField()

    password = forms.CharField(
        widget=forms.PasswordInput,
        min_length=8
    )

    confirm_password = forms.CharField(
        widget=forms.PasswordInput
    )

    company_name = forms.CharField(
        max_length=200
    )

    registration_number = forms.CharField(
        max_length=100
    )

    gstin = forms.CharField(
        max_length=15,
        min_length=15
    )

    authorized_person = forms.CharField(
        max_length=150
    )

    phone = forms.CharField(
        max_length=15
    )

    address = forms.CharField(
        widget=forms.Textarea
    )

    user_type = forms.ChoiceField(
        choices=Company.USER_TYPES
    )

    permit_document = forms.FileField(
        required=False,
        label='Permit / Business Document (PDF/JPG/PNG)'
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()

        if User.objects.filter(
            username__iexact=username
        ).exists():
            raise forms.ValidationError(
                'Username already exists.'
            )

        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        if User.objects.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError(
                'Email already registered.'
            )

        return email

    def clean_gstin(self):
        gstin = self.cleaned_data['gstin'].strip().upper()

        if Company.objects.filter(
            gstin=gstin
        ).exists():
            raise forms.ValidationError(
                'This GSTIN is already registered.'
            )

        return gstin

    def clean_registration_number(self):
        number = self.cleaned_data[
            'registration_number'
        ].strip().upper()

        if Company.objects.filter(
            registration_number=number
        ).exists():
            raise forms.ValidationError(
                'This registration number is already registered.'
            )

        return number

    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()

        if not phone.isdigit():
            raise forms.ValidationError(
                'Enter a valid phone number.'
            )

        if len(phone) < 10 or len(phone) > 15:
            raise forms.ValidationError(
                'Phone number must contain 10 to 15 digits.'
            )

        return phone

    def clean_permit_document(self):
        document = self.cleaned_data.get('permit_document')
        if document:
            allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg']
            import os
            ext = os.path.splitext(document.name)[1].lower()
            if ext not in allowed_extensions:
                raise forms.ValidationError(
                    'Invalid file format. Please upload a PDF or image file (.pdf, .png, .jpg, .jpeg).'
                )
            if document.size > 10 * 1024 * 1024:
                raise forms.ValidationError(
                    'File size exceeds 10MB limit. Please upload a smaller document.'
                )
        return document

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get(
            'confirm_password'
        )

        if password:
            try:
                validate_password(
                    password
                )
            except forms.ValidationError as error:
                self.add_error(
                    'password',
                    error
                )

        if password and confirm_password:
            if password != confirm_password:
                self.add_error(
                    'confirm_password',
                    'Passwords do not match.'
                )

        return cleaned_data