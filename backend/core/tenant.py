from rest_framework.exceptions import PermissionDenied

from .models import Membership


def current_membership(user):
    membership = Membership.objects.select_related("organization").filter(user=user).first()
    if not membership:
        raise PermissionDenied("User is not assigned to an organization.")
    return membership

