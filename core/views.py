from django.http import JsonResponse

from .api import endpoint


@endpoint(["GET"], auth=False)
def service_info(request):
    return JsonResponse({
        "service": "the-we-system-server",
        "status": "ok",
        "apiVersion": "v1",
        "health": "/api/v1/health",
    })


@endpoint(["GET"], auth=False)
def health(request):
    return JsonResponse({"status": "ok"})
