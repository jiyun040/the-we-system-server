from django.contrib.auth import get_user_model


DESIGNATED_ADMIN_USERNAME = "we81048"
DESIGNATED_ADMIN_NAME = "김효민"
DESIGNATED_ADMIN_DEPARTMENT = "경리부"
DESIGNATED_ADMIN_POSITION = "대리"


def matches_designated_admin_profile(username, name, department, position):
    return (
        username.strip().lower() == DESIGNATED_ADMIN_USERNAME
        and name.strip() == DESIGNATED_ADMIN_NAME
        and department.strip() == DESIGNATED_ADMIN_DEPARTMENT
        and position.strip() == DESIGNATED_ADMIN_POSITION
    )


def ensure_designated_admin_access(user):
    """Restore the designated administrator flag if deployment data missed it."""
    if user is None or user.is_staff or not user.is_active:
        return user

    department_name = user.department.name if user.department else ""
    if not matches_designated_admin_profile(
        user.username,
        user.first_name,
        department_name,
        user.position,
    ):
        return user

    user_model = get_user_model()
    user_model.objects.filter(pk=user.pk, is_staff=False).update(is_staff=True)
    user.is_staff = True
    return user
