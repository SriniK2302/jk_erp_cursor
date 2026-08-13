import threading

_local = threading.local()


def set_audit_user(user):
    _local.user = user


def get_audit_user():
    return getattr(_local, "user", None)


def clear_audit_user():
    if hasattr(_local, "user"):
        del _local.user
