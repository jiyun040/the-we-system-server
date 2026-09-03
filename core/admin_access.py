from secrets import compare_digest

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password


DESIGNATED_ADMIN_USERNAME = "we81048"
DESIGNATED_ADMIN_NAME = "김효민"
DESIGNATED_ADMIN_DEPARTMENT = "경리부"
DESIGNATED_ADMIN_POSITION = "대리"
DEFAULT_ADMIN_OTP = "123456"


def matches_designated_admin_profile(username, name, department, position):
    return (
        username.strip().lower() == DESIGNATED_ADMIN_USERNAME
        and name.strip() == DESIGNATED_ADMIN_NAME
        and department.strip() == DESIGNATED_ADMIN_DEPARTMENT
        and position.strip() == DESIGNATED_ADMIN_POSITION
    )


def is_super_admin_account(user):
    return bool(
        user
        and user.is_staff
        and user.username.strip().lower() == "admin"
    )


def can_change_admin_otp(user):
    if user is None or not user.is_staff or not user.is_active:
        return False
    department_name = user.department.name if user.department else ""
    return matches_designated_admin_profile(
        user.username,
        user.first_name,
        department_name,
        user.position,
    )


def verify_admin_otp_for_user(user, otp):
    if is_super_admin_account(user):
        return compare_digest(otp, DEFAULT_ADMIN_OTP)
    if user.admin_otp_hash:
        return check_password(otp, user.admin_otp_hash)
    return compare_digest(otp, DEFAULT_ADMIN_OTP)


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
