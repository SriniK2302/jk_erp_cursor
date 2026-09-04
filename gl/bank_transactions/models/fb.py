from django.db import models


class Fb(models.Model):
    fb_code = models.CharField(max_length=20, unique=True)
    fb_desc = models.CharField(max_length=255, blank=True, null=True)
    entity = models.CharField(max_length=100)

    class Meta:
        managed = False  # table already exists in the database; Django never alters it
        db_table = "fbs"
        ordering = ["fb_code"]

    def __str__(self):
        return self.fb_code
    