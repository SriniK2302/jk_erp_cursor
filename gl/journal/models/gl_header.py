from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class GlHeader(models.Model):
    """Journal header: one logical GL transaction (voucher / document)."""

    class Source(models.TextChoices):
        SALES = "Sales", "Sales"
        PURCHASES = "Purchases", "Purchases"
        PAYROLL = "Payroll", "Payroll"
        FA = "FA", "FA"
        JV = "JV", "JV"
        CASH = "Cash", "Cash"
        BANK = "Bank", "Bank"
        OTHER = "Other", "Other"

    class Status(models.TextChoices):
        FRESH = "fresh", "Fresh"
        AUTHORISED = "authorised", "Authorised"

    rec_id = models.BigAutoField(primary_key=True)
    tran_date = models.DateField(db_index=True)
    tran_id = models.CharField(
        max_length=40,
        db_index=True,
        help_text="Business transaction id (document / batch id within source).",
    )
    source = models.CharField(max_length=20, choices=Source.choices, db_index=True)
    narration = models.TextField(blank=True, default="")
    ym = models.CharField(
        max_length=12,
        blank=True,
        default="",
        db_index=True,
        help_text="Reporting month key, e.g. M YYYY MM as stored by your convention.",
    )
    line_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.FRESH,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_gl_headers",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gl_header"
        ordering = ["-tran_date", "-rec_id"]

    def __str__(self):
        return f"{self.source} {self.tran_id} @ {self.tran_date}"

    def save(self, *args, **kwargs):
        if self.pk:
            prior = GlHeader.objects.filter(pk=self.pk).values("status").first()
            if prior and prior["status"] == self.Status.AUTHORISED:
                raise ValidationError(
                    "Authorised GL header cannot be edited. Create a reversal/adjustment entry instead."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.AUTHORISED:
            raise ValidationError(
                "Authorised GL header cannot be deleted. Create a reversal entry instead."
            )
        return super().delete(*args, **kwargs)
