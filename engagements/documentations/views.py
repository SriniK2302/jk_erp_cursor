from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import get_valid_filename

from engagements.models import (
    EngagementDocumentationMap,
    EngagementDivisionDocumentationMap,
    FirmReferenceDocument,
)
from sales.client_classifications.models import ClientClassification

from .forms import EngagementDocumentationForm, FirmReferenceDocumentForm
from .word_template import word_template_content_type
from .map_cleanup import (
    delete_maps_for_removed_setup_classifications,
    notify_documentation_map_cascade,
)
from .models import EngagementDocumentation


@login_required
def reference_documents(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete_reference_document":
            doc = get_object_or_404(
                FirmReferenceDocument,
                pk=request.POST.get("pk"),
            )
            doc.delete()
            messages.success(request, "Reference document removed.")
            return redirect("reference_documents")
        return redirect("reference_documents")

    qs = FirmReferenceDocument.objects.select_related("created_by")
    if not request.GET.get("include_inactive"):
        qs = qs.filter(is_active=True)

    filter_q = (request.GET.get("q") or "").strip()
    if filter_q:
        q_parts = [
            Q(title__icontains=filter_q),
            Q(description__icontains=filter_q),
            Q(tags__icontains=filter_q),
            Q(original_filename__icontains=filter_q),
            Q(category__icontains=filter_q),
            Q(created_by__username__icontains=filter_q),
        ]
        combined = q_parts[0]
        for part in q_parts[1:]:
            combined |= part
        qs = qs.filter(combined)

    documents = qs.order_by("category", "title")
    return render(
        request,
        "documentations/reference_documents.html",
        {
            "documents": documents,
            "filter_q": filter_q,
            "filter_include_inactive": bool(request.GET.get("include_inactive")),
        },
    )


@login_required
def reference_document_create(request):
    if request.method == "POST":
        form = FirmReferenceDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, "Reference document added.")
            return redirect("reference_documents")
    else:
        form = FirmReferenceDocumentForm()
    return render(
        request,
        "documentations/reference_document_form.html",
        {
            "form": form,
            "heading": "Add reference document",
            "cancel_url": reverse("reference_documents"),
        },
    )


@login_required
def reference_document_edit(request, pk):
    doc = get_object_or_404(FirmReferenceDocument, pk=pk)
    if request.method == "POST":
        form = FirmReferenceDocumentForm(request.POST, request.FILES, instance=doc)
        if form.is_valid():
            form.save()
            messages.success(request, "Reference document updated.")
            return redirect("reference_documents")
    else:
        form = FirmReferenceDocumentForm(instance=doc)
    return render(
        request,
        "documentations/reference_document_form.html",
        {
            "form": form,
            "heading": "Edit reference document",
            "document": doc,
            "cancel_url": reverse("reference_documents"),
        },
    )


@login_required
def reference_document_download(request, pk):
    doc = get_object_or_404(FirmReferenceDocument, pk=pk)
    if not doc.file:
        raise Http404
    try:
        fh = doc.file.open("rb")
    except OSError:
        raise Http404
    download_name = get_valid_filename(doc.original_filename) or "reference"
    return FileResponse(
        fh,
        as_attachment=True,
        filename=download_name,
    )


@login_required
def engagement_documentations(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            documentation = get_object_or_404(
                EngagementDocumentation,
                pk=request.POST.get("pk"),
            )
            if documentation.engagement_maps.exists() or documentation.division_maps.exists():
                messages.error(
                    request,
                    "This documentation is mapped to an engagement or engagement division and cannot be deleted.",
                )
                return redirect("engagement_documentations")
            documentation.delete()
            return redirect("engagement_documentations")
        return redirect("engagement_documentations")

    documentations = (
        EngagementDocumentation.objects.annotate(
            mapped_to_engagement=Exists(
                EngagementDocumentationMap.objects.filter(
                    documentation_id=OuterRef("pk"),
                )
            ),
            mapped_to_division=Exists(
                EngagementDivisionDocumentationMap.objects.filter(
                    documentation_id=OuterRef("pk"),
                )
            ),
        )
        .prefetch_related(
            Prefetch(
                "applicable_classifications",
                queryset=ClientClassification.objects.order_by("classification_name"),
            )
        )
        .all()
    )
    return render(
        request,
        "documentations/engagement_documentations.html",
        {
            "documentations": documentations,
        },
    )


def _engagement_documentation_form_view(request, instance=None):
    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url and not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        next_url = None

    if request.method == "POST":
        if (
            request.POST.get("form_action") == "delete_word_template"
            and instance is not None
            and instance.pk
        ):
            doc = get_object_or_404(EngagementDocumentation, pk=instance.pk)
            if doc.word_template:
                doc.word_template.delete(save=False)
            doc.word_template = None
            doc.save(update_fields=["word_template", "updated_on"])
            messages.success(request, "Word template removed.")
            edit_url = reverse("engagement_documentation_edit", kwargs={"pk": doc.pk})
            if next_url:
                edit_url = f"{edit_url}?{urlencode({'next': next_url})}"
            return redirect(edit_url)

        old_classification_ids = None
        if instance is not None and instance.pk:
            old_classification_ids = set(
                instance.applicable_classifications.values_list("pk", flat=True)
            )
        form = EngagementDocumentationForm(
            request.POST,
            request.FILES,
            instance=instance,
        )
        if form.is_valid():
            documentation = form.save(commit=False)
            if instance is None:
                documentation.created_by = request.user
            documentation.save()
            form.save_m2m()
            if old_classification_ids is not None:
                new_ids = set(
                    documentation.applicable_classifications.values_list(
                        "pk", flat=True
                    )
                )
                removed = old_classification_ids - new_ids
                if removed:
                    summary = delete_maps_for_removed_setup_classifications(
                        documentation, removed
                    )
                    notify_documentation_map_cascade(request, summary)
            return redirect(next_url or "engagement_documentations")
    else:
        form = EngagementDocumentationForm(instance=instance)

    return render(
        request,
        "documentations/engagement_documentation_form.html",
        {
            "form": form,
            "documentation": instance,
            "cancel_url": next_url or reverse("engagement_documentations"),
            "next_url": next_url,
        },
    )


@login_required
def engagement_documentation_create(request):
    return _engagement_documentation_form_view(request)


@login_required
def engagement_documentation_edit(request, pk):
    documentation = get_object_or_404(EngagementDocumentation, pk=pk)
    return _engagement_documentation_form_view(request, instance=documentation)


@login_required
def engagement_documentation_word_template_download(request, pk):
    documentation = get_object_or_404(EngagementDocumentation, pk=pk)
    if not documentation.word_template:
        raise Http404
    try:
        fh = documentation.word_template.open("rb")
    except OSError:
        raise Http404
    raw_name = (
        getattr(documentation.word_template, "name", "") or ""
    ).replace("\\", "/").rsplit("/", 1)[-1]
    download_name = get_valid_filename(raw_name) or "template.docx"
    content_type = word_template_content_type(download_name)
    return FileResponse(
        fh,
        as_attachment=True,
        filename=download_name,
        content_type=content_type,
    )
