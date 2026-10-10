from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "message", "lue", "date_creation")
    list_filter = ("lue",)
    list_select_related = ("destinataire",)
