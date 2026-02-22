import django_filters
from django.contrib.auth import get_user_model

User = get_user_model()


class UserFilter(django_filters.FilterSet):
    """
    Filters for the user list.
    Used by AllUsersListView and AgentListView.
    """
    role = django_filters.ChoiceFilter(choices=User.Role.choices)
    status = django_filters.ChoiceFilter(choices=User.AccountStatus.choices)
    branch = django_filters.UUIDFilter(field_name="branch__id")
    search = django_filters.CharFilter(method="filter_search")
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = User
        fields = ["role", "status", "branch"]

    def filter_search(self, queryset, name, value):
        """Search by first name, last name or email."""
        from django.db.models import Q
        return queryset.filter(
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email__icontains=value)
        )


class DateRangeFilter(django_filters.FilterSet):
    """
    Mixin for date range filtering.
    Inherit this in any FilterSet that needs to filter by date.
    """
    date_after = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    date_before = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")