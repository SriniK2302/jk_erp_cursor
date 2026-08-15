from sales.services.models import Service


def certification_service_queryset():
    return Service.objects.filter(service_desc__icontains="certification").order_by(
        "service_desc", "service_code"
    )
