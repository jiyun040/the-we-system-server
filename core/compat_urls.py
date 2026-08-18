from django.urls import path

from . import views, views_approvals

urlpatterns = [
    path("", views.service_info, name="service-info"),
    path("approvals/dashboard", views_approvals.dashboard, name="compat-approval-dashboard"),
    path("approvals/<str:document_id>/approve", views_approvals.act_on_document, {"action": "approve"}, name="compat-document-approve"),
]
