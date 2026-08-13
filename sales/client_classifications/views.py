from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ClientClassificationForm
from .models import ClientClassification


@login_required
def client_classifications(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            classification = get_object_or_404(
                ClientClassification,
                pk=request.POST.get("pk"),
            )
            classification.delete()
            return redirect("client_classifications")
        return redirect("client_classifications")

    return render(
        request,
        "client_classifications/client_classifications.html",
        {
            "classifications": ClientClassification.objects.select_related(
                "created_by"
            ).all(),
        },
    )


def _client_classification_form_view(request, instance=None):
    if request.method == "POST":
        form = ClientClassificationForm(request.POST, instance=instance)
        if form.is_valid():
            classification = form.save(commit=False)
            if instance is None:
                classification.created_by = request.user
            classification.save()
            return redirect("client_classifications")
    else:
        form = ClientClassificationForm(instance=instance)

    return render(
        request,
        "client_classifications/client_classification_form.html",
        {
            "form": form,
            "classification": instance,
        },
    )


@login_required
def client_classification_create(request):
    return _client_classification_form_view(request)


@login_required
def client_classification_edit(request, pk):
    classification = get_object_or_404(ClientClassification, pk=pk)
    return _client_classification_form_view(request, instance=classification)
