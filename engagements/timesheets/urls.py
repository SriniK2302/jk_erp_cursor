from django.urls import path

from . import views

urlpatterns = [
    path("timer/stop/", views.timer_stop, name="timer_stop"),
    path("timer/recent-tasks/", views.timer_recent_tasks, name="timer_recent_tasks"),
    path(
        "engagements/<int:engagement_pk>/timer/start/",
        views.timer_start_engagement,
        name="timer_start_engagement",
    ),
    path(
        "divisions/<int:division_pk>/timer/start/",
        views.timer_start_division,
        name="timer_start_division",
    ),
    path(
        "engagements/<int:engagement_pk>/work-areas/<int:work_area_pk>/timer/start/",
        views.timer_start_engagement_work_area,
        name="timer_start_engagement_work_area",
    ),
    path(
        "divisions/<int:division_pk>/work-areas/<int:work_area_pk>/timer/start/",
        views.timer_start_division_work_area,
        name="timer_start_division_work_area",
    ),
    path("my-time-log/", views.my_time_log, name="my_time_log"),
]
