from django.db import models


class InvoiceStatus(models.TextChoices):
    """Invoice posting lifecycle: must be Authorised before GL."""

    FRESH = "fresh", "Fresh"
    AUTHORISED = "authorised", "Authorised"
