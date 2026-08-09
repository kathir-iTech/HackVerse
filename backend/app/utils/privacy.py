import re

def scrub_pii(text: str) -> str:
    """Remove personally identifiable information before sending to external LLMs."""
    if not text:
        return text
    # Mask 12-digit Aadhaar numbers (with or without spaces)
    text = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[AADHAAR]', text)
    # Mask PAN cards (5 letters, 4 digits, 1 letter)
    text = re.sub(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', '[PAN]', text)
    # Mask Indian mobile numbers
    text = re.sub(r'\b(?:\+91[\s-]?)?[6-9]\d{9}\b', '[PHONE]', text)
    # Mask UPI IDs
    text = re.sub(r'\b[a-zA-Z0-9._-]+@[a-zA-Z]{2,}\b', '[UPI_ID]', text)
    # Mask email addresses  
    text = re.sub(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
    return text
