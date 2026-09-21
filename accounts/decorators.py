from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def supplier_required(view_func):
    """
    Decorator for views that checks that the logged-in user is a verified supplier
    or dual-role enterprise ('both'). Pure buyers are denied access.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to access the Supplier Portal.")
            return redirect('login')

        company = getattr(request.user, 'company', None)
        if not company or not company.can_sell:
            messages.error(
                request,
                "Access Denied: Your account is registered as a Buyer-only enterprise. "
                "Only Suppliers and Dual-Role enterprises can list materials and access the Supplier Hub."
            )
            return redirect('index')

        return view_func(request, *args, **kwargs)
    return _wrapped_view


def buyer_required(view_func):
    """
    Decorator for views that checks that the logged-in user is a buyer
    or dual-role enterprise ('both'). Pure suppliers are denied access.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to access Buyer Procurement.")
            return redirect('login')

        company = getattr(request.user, 'company', None)
        if not company or not company.can_buy:
            messages.error(
                request,
                "Access Denied: Your account is registered as a Supplier-only enterprise. "
                "Only Buyers and Dual-Role enterprises can place procurement orders."
            )
            return redirect('dashboard')

        return view_func(request, *args, **kwargs)
    return _wrapped_view
