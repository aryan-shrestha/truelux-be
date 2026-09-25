from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsOwnerOrAdmin(BasePermission):
    owner_field = "user"

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        # Staff are admitted so that adding a staff endpoint later does not require
        # changing this class, even though Phase 1 routes staff through the admin.
        if request.user.is_staff:
            return True
        return bool(getattr(obj, self.owner_field) == request.user)
