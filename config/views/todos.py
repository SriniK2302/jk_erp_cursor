from .utility_jobs import *  # noqa: F403
from .utility_jobs import (
    _DUPLICATE_JOBS,
    _DUPLICATE_JOBS_LOCK,
    _SIMILAR_JOBS,
    _SIMILAR_JOBS_LOCK,
    _SIMILAR_REF_JOBS,
    _SIMILAR_REF_JOBS_LOCK,
    _EXCEL_IMPORT_JOBS,
    _EXCEL_IMPORT_JOBS_LOCK,
    _MOVE_ALL_JOBS,
    _MOVE_ALL_JOBS_LOCK,
    _start_duplicate_job,
    _start_similar_files_job,
    _start_similar_to_reference_job,
    _start_excel_import_job,
    _start_move_all_files_job,
    _save_excel_import_preferences,
    _is_truthy_form_value,
    _excel_import_mapping_warning,
)


def _user_todo_queryset(user):
    from config.models import UserTodo

    return UserTodo.objects.filter(user=user).order_by(
        "is_completed",
        F("target_date").asc(nulls_last=True),
        "-created_on",
    )


@login_required
def my_todos(request):
    todos = _user_todo_queryset(request.user)
    return render(
        request,
        "config/my_todos.html",
        {
            "todos": todos,
            "today": timezone.localdate(),
        },
    )


@login_required
def my_todo_create(request):
    from config.models import UserTodo

    if request.method == "POST":
        form = UserTodoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()
            messages.success(request, "Task added.")
            return redirect("my_todos")
    else:
        form = UserTodoForm()
    return render(request, "config/my_todo_form.html", {"form": form, "todo": None})


@login_required
def my_todo_edit(request, pk: int):
    from config.models import UserTodo

    todo = get_object_or_404(UserTodo, pk=pk, user=request.user)
    if request.method == "POST":
        form = UserTodoForm(request.POST, instance=todo)
        if form.is_valid():
            form.save()
            messages.success(request, "Task updated.")
            return redirect("my_todos")
    else:
        form = UserTodoForm(instance=todo)
    return render(request, "config/my_todo_form.html", {"form": form, "todo": todo})


@login_required
@require_POST
def my_todo_delete(request, pk: int):
    from config.models import UserTodo

    todo = get_object_or_404(UserTodo, pk=pk, user=request.user)
    todo.delete()
    messages.success(request, "Task removed.")
    return redirect("my_todos")


@login_required
@require_POST
def my_todo_toggle(request, pk: int):
    from config.models import UserTodo

    todo = get_object_or_404(UserTodo, pk=pk, user=request.user)
    todo.is_completed = not todo.is_completed
    todo.save(update_fields=["is_completed", "updated_on"])
    messages.success(
        request, "Marked complete." if todo.is_completed else "Reopened task."
    )
    return redirect("my_todos")

