from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_GET

from .forms import ClientForm, ClientTaxProfileForm
from .models import Client, ClientDocument, ClientTaxProfile

_CLIENT_DOCUMENT_UPLOAD_LIMIT = 30


def _ordered_client_pks():
    return list(Client.objects.order_by("client_name", "id").values_list("pk", flat=True))


def _client_nav_context(client, *, url_name: str):
    """First / prev / next / last for ordered client list; url_name is client_edit or client_tax_profile."""
    pks = _ordered_client_pks()
    search_mode = "tax_profile" if url_name == "client_tax_profile" else "edit"

    def href(pk):
        return reverse(url_name, args=[pk]) if pk else None

    if not client or not pks:
        return {
            "mode": "browse",
            "url_name": url_name,
            "search_mode": search_mode,
            "first_pk": None,
            "prev_pk": None,
            "next_pk": None,
            "last_pk": None,
            "first_href": None,
            "prev_href": None,
            "next_href": None,
            "last_href": None,
            "current_pk": getattr(client, "pk", None),
            "index": 0,
            "count": len(pks),
        }
    try:
        idx = pks.index(client.pk)
    except ValueError:
        fp, lp = (pks[0], pks[-1]) if pks else (None, None)
        return {
            "mode": "browse",
            "url_name": url_name,
            "search_mode": search_mode,
            "first_pk": fp,
            "prev_pk": None,
            "next_pk": None,
            "last_pk": lp,
            "first_href": href(fp),
            "prev_href": None,
            "next_href": None,
            "last_href": href(lp),
            "current_pk": client.pk,
            "index": 0,
            "count": len(pks),
        }
    first_pk = pks[0]
    prev_pk = pks[idx - 1] if idx > 0 else None
    next_pk = pks[idx + 1] if idx < len(pks) - 1 else None
    last_pk = pks[-1]
    return {
        "mode": "browse",
        "url_name": url_name,
        "search_mode": search_mode,
        "first_pk": first_pk,
        "prev_pk": prev_pk,
        "next_pk": next_pk,
        "last_pk": last_pk,
        "first_href": href(first_pk),
        "prev_href": href(prev_pk),
        "next_href": href(next_pk),
        "last_href": href(last_pk),
        "current_pk": client.pk,
        "index": idx + 1,
        "count": len(pks),
    }


@login_required
def clients(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            client = get_object_or_404(Client, pk=request.POST.get("pk"))
            client.delete()
            return redirect("clients")
        return redirect("clients")

    return render(
        request,
        "clients/clients.html",
        {
            "clients": Client.objects.select_related("created_by", "classification").all(),
        },
    )


def _client_form_view(request, instance=None):
    if request.method == "POST":
        form = ClientForm(request.POST, instance=instance)
        if form.is_valid():
            client = form.save(commit=False)
            if instance is None:
                client.created_by = request.user
            client.save()
            next_url = request.GET.get("next")
            if next_url:
                sep = "&" if "?" in next_url else "?"
                return redirect(f"{next_url}{sep}new_client={client.pk}")
            return redirect("clients")
    else:
        form = ClientForm(instance=instance)

    if instance:
        client_nav = _client_nav_context(instance, url_name="client_edit")
    else:
        client_nav = {"mode": "create", "url_name": "client_edit", "search_mode": "edit"}

    return render(
        request,
        "clients/client_form.html",
        {
            "form": form,
            "client": instance,
            "client_nav": client_nav,
        },
    )


@login_required
def client_create(request):
    return _client_form_view(request)


@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return _client_form_view(request, instance=client)


@login_required
def client_tax_profile(request, pk):
    client = get_object_or_404(Client, pk=pk)
    instance = ClientTaxProfile.objects.filter(client=client).first()
    if request.method == "POST":
        form = ClientTaxProfileForm(request.POST, instance=instance)
        if form.is_valid():
            profile = form.save(commit=False)
            if instance is None:
                profile.client = client
                profile.created_by = request.user
            profile.save()
            return redirect("clients")
    else:
        form = ClientTaxProfileForm(instance=instance)
    client_nav = _client_nav_context(client, url_name="client_tax_profile")
    return render(
        request,
        "clients/client_tax_profile_form.html",
        {
            "form": form,
            "client": client,
            "tax_profile": instance,
            "client_nav": client_nav,
        },
    )


@login_required
def client_documents(request, pk):
    client = get_object_or_404(
        Client.objects.select_related("classification"), pk=pk
    )
    documents_url = reverse("client_documents", args=[client.pk])

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "upload_document":
            files = request.FILES.getlist("files")
            document_label = (request.POST.get("document_label") or "").strip()[:120]
            notes = (request.POST.get("notes") or "").strip()
            if not files:
                messages.warning(request, "No files were selected.")
            else:
                n = 0
                with transaction.atomic():
                    for upload in files[:_CLIENT_DOCUMENT_UPLOAD_LIMIT]:
                        ClientDocument.objects.create(
                            client=client,
                            file=upload,
                            original_filename=(upload.name or "file")[:255],
                            document_label=document_label,
                            notes=notes,
                            created_by=request.user,
                        )
                        n += 1
                messages.success(request, f"Added {n} file(s).")
            return redirect(documents_url)
        if action == "delete_document":
            document = get_object_or_404(
                ClientDocument, pk=request.POST.get("pk"), client=client
            )
            document.delete()
            messages.success(request, "Document removed.")
            return redirect(documents_url)
        return redirect(documents_url)

    documents = client.documents.select_related("created_by").order_by(
        "document_label", "original_filename", "pk"
    )
    return render(
        request,
        "clients/client_documents.html",
        {
            "client": client,
            "documents": documents,
            "client_nav": _client_nav_context(client, url_name="client_edit"),
        },
    )


@login_required
@require_GET
def client_document_download(request, pk, document_pk):
    client = get_object_or_404(Client, pk=pk)
    document = get_object_or_404(ClientDocument, pk=document_pk, client=client)
    if not document.file:
        raise Http404
    safe_name = get_valid_filename(document.original_filename) or "download"
    inline = (request.GET.get("disposition") or "").strip().lower() == "inline"
    if inline and not document.can_open_inline:
        inline = False
    try:
        file_handle = document.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=not inline,
        filename=safe_name,
    )


@login_required
def client_nav_search(request):
    q = (request.GET.get("q") or "").strip()
    mode = (request.GET.get("mode") or "edit").strip().lower()
    if mode not in {"edit", "tax_profile"}:
        mode = "edit"
    url_name = "client_tax_profile" if mode == "tax_profile" else "client_edit"

    qs = Client.objects.order_by("client_name", "id")
    if q:
        qs = qs.filter(
            Q(client_name__icontains=q)
            | Q(client_code__icontains=q)
            | Q(client_short_name__icontains=q)
        )
    results = [
        {
            "id": c.pk,
            "text": c.display_name,
            "href": reverse(url_name, args=[c.pk]),
        }
        for c in qs[:40]
    ]
    return JsonResponse({"results": results})


