import re
from django.utils import timezone

# Regular expressions for industrial registration identifiers (CIN / Factory Permit / Standard format)
# 1. Indian Corporate Identity Number (CIN): e.g. U25190GJ2021PTC120444
CIN_PATTERN = re.compile(r'^[UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$', re.IGNORECASE)
# 2. Industrial / PCB Permit pattern: e.g. GPCB-WM-22910 or REG-GJ-2291 or IND-9821
STANDARD_REG_PATTERN = re.compile(r'^(REG|GPCB|MSME|IND|CIN)-[A-Z0-9-]{4,20}$', re.IGNORECASE)


def is_valid_registration_structure(reg_number: str) -> bool:
    """
    Validates whether the given registration number matches standard corporate
    or industrial pollution control board identification formats.
    """
    if not reg_number:
        return False
    clean_number = reg_number.strip().upper()
    return bool(CIN_PATTERN.match(clean_number) or STANDARD_REG_PATTERN.match(clean_number))


def verify_company_registration(company) -> dict:
    """
    Automated Demonstration Verification Engine.
    
    RULES:
    1. If permit document is uploaded AND registration number satisfies the
       structural pattern -> AUTO_VERIFIED.
    2. If permit document is uploaded but registration pattern does not match -> FLAGGED.
    3. If permit document is missing -> PENDING (requires manual documentation).
    
    DISCLAIMER:
    This is a demonstration verification utility for educational evaluation.
    It performs structural pattern and file checks rather than querying
    live state pollution control or MCA government servers.
    """
    has_permit = bool(company.permit_document and company.permit_document.name)
    reg_valid = is_valid_registration_structure(company.registration_number)

    if has_permit and reg_valid:
        company.verification_status = 'auto_verified'
        company.verified_at = timezone.now()
        company.save(update_fields=['verification_status', 'verified_at'])
        return {
            'status': 'auto_verified',
            'verified': True,
            'message': 'Automated demo verification successful: permit file present and registration format compliant.'
        }
    elif has_permit and not reg_valid:
        company.verification_status = 'flagged'
        company.save(update_fields=['verification_status'])
        return {
            'status': 'flagged',
            'verified': False,
            'message': 'Flagged for administrator review: registration number format does not match standard CIN/GPCB pattern.'
        }
    else:
        company.verification_status = 'pending'
        company.save(update_fields=['verification_status'])
        return {
            'status': 'pending',
            'verified': False,
            'message': 'Pending verification: permit document was not uploaded during registration.'
        }
