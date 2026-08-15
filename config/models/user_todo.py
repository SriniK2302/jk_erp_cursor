from django.conf import settings
from django.db import models


class UserTodo(models.Model):
    """Personal to-do item for a login user (not shared across users)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="todos",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional due or reminder date.",
    )
    is_completed = models.BooleanField(default=False)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_todos"
        ordering = ["-created_on"]

    def __str__(self):
        return self.title
