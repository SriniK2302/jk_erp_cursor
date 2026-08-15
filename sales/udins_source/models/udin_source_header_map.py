from django.conf import settings
from django.db import models


class UdinSourceHeaderMap(models.Model):
    key = models.CharField(max_length=40, unique=True, default="default")
    mapping_json = models.JSONField(default=dict)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_udin_source_header_maps",
        null=True,
        blank=True,
    )
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "udins_source_header_maps"

    @staticmethod
    def default_mapping():
        return {
            "s_no": ["S.No.", "S No", "Sl No", "No"],
            "udin": ["UDIN"],
            "mrn": ["MRN"],
            "firm": ["Firm"],
            "document_type": ["Document Type"],
            "document_sub_type": ["Document Sub-Type"],
            "other_doc": ["OtherDoc", "Other Doc"],
            "document_description": ["Document Description"],
            "date_of_signing_of_document": ["Date of Signing of Document"],
            "ay_fy": ["AY/FY", "AY FY"],
            "created_date_time": ["Created Date/Time", "Created Date Time"],
            "remarks": ["Remarks"],
            "status": ["Status"],
            "particulars_1": ["Particulars 1"],
            "figures_values_1": ["Figures/Values 1", "Figures/Values  1"],
            "particulars_2": ["Particulars 2"],
            "figures_values_2": ["Figures/Values 2", "Figures/Values  2"],
            "particulars_3": ["Particulars 3"],
            "figures_values_3": ["Figures/Values 3", "Figures/Values  3"],
            "particulars_4": ["Particulars 4"],
            "figures_values_4": ["Figures/Values 4", "Figures/Values  4"],
        }

    @classmethod
    def get_solo(cls):
        row, created = cls.objects.get_or_create(key="default")
        if created or not row.mapping_json:
            row.mapping_json = cls.default_mapping()
            row.save(update_fields=["mapping_json", "updated_on"])
        return row
