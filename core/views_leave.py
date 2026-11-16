from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from apps.organizations.tenancy import scope_queryset
from . import roles
from .models import Employee
from .permissions import employee_access, get_employee_profile, require_employee_profile
from .services.leave_balances import balance


@login_required
def balances(request, pk=None):
    emp_profile = get_employee_profile(request.user)
    can_view_all = request.user.has_perm(roles.VIEW_ALL_LEAVES) or request.user.is_staff
    all_employees = scope_queryset(Employee.objects.filter(is_active=True).order_by("name"), request.user) if can_view_all else None

    if pk is not None:
        employee = get_object_or_404(scope_queryset(Employee.objects.all(), request.user), pk=pk)
    elif can_view_all and request.GET.get("emp"):
        employee = get_object_or_404(scope_queryset(Employee.objects.all(), request.user), pk=request.GET.get("emp"))
    elif emp_profile is not None:
        employee = emp_profile
    elif can_view_all:
        employee = all_employees.first()
        if not employee:
            from django.http import Http404
            raise Http404("No employees found.")
    else:
        employee = require_employee_profile(request.user, active=False)

    if not employee_access(request.user, employee).employment:
        raise PermissionDenied
    year = timezone.localdate().year
    rows = [balance(item) for item in employee.leave_entitlements.filter(year=year)]
    return render(request, "leave_balances.html", {
        "employee": employee,
        "balances": rows,
        "year": year,
        "all_employees": all_employees,
    })


@login_required
def cancel_pending(request, pk):
    from django.contrib import messages
    from django.core.exceptions import ValidationError
    from django.shortcuts import redirect
    from django.views.decorators.http import require_POST
    from .models import LeaveApplication
    from .services.leave import cancel_leave
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    item = get_object_or_404(LeaveApplication, pk=pk, emp__user=request.user)
    try:
        cancel_leave(item, by=request.user, note=request.POST.get("reason", ""))
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Pending leave cancelled.")
    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("leaves_list")
