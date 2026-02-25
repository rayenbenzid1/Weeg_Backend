from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer
from .serializers import (
    CustomerListSerializer,
    CustomerDetailSerializer,
    CustomerWriteSerializer,
)


class CustomerListView(APIView):
    """
    GET  /api/customers/
        Query params:
            search=<str>       — name or account_code
            area_code=<str>    — exact match
            ordering=<field>   — customer_name | account_code | created_at (prefix - for DESC)
            page=<int>
            page_size=<int>    — default 50, max 200

    POST /api/customers/       — manager / admin only
    """

    permission_classes = [IsAuthenticated]
    ALLOWED_ORDERINGS = {
        "customer_name", "-customer_name",
        "account_code", "-account_code",
        "created_at", "-created_at",
    }

    def get(self, request):
        qs = Customer.objects.filter(company=request.user.company)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(customer_name__icontains=search) |
                Q(account_code__icontains=search)
            )

        area_code = request.query_params.get("area_code", "").strip()
        if area_code:
            qs = qs.filter(area_code=area_code)

        ordering = request.query_params.get("ordering", "customer_name")
        if ordering in self.ALLOWED_ORDERINGS:
            qs = qs.order_by(ordering)

        total_count = qs.count()
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        start = (page - 1) * page_size
        qs_page = qs[start: start + page_size]

        return Response({
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "customers": CustomerListSerializer(qs_page, many=True).data,
        })

    def post(self, request):
        if not (request.user.is_admin or request.user.is_manager):
            return Response(
                {"error": "Only managers and administrators can create customers."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = CustomerWriteSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        customer = serializer.save(company=request.user.company)
        return Response(
            CustomerDetailSerializer(customer).data,
            status=status.HTTP_201_CREATED,
        )


class CustomerDetailView(APIView):
    """
    GET    /api/customers/{id}/
    PATCH  /api/customers/{id}/   — manager / admin only
    DELETE /api/customers/{id}/   — admin only
    """

    permission_classes = [IsAuthenticated]

    def _get_customer(self, customer_id, company):
        try:
            return Customer.objects.get(id=customer_id, company=company)
        except Customer.DoesNotExist:
            return None

    def get(self, request, customer_id):
        customer = self._get_customer(customer_id, request.user.company)
        if not customer:
            return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CustomerDetailSerializer(customer).data)

    def patch(self, request, customer_id):
        if not (request.user.is_admin or request.user.is_manager):
            return Response({"error": "Insufficient permissions."}, status=status.HTTP_403_FORBIDDEN)
        customer = self._get_customer(customer_id, request.user.company)
        if not customer:
            return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CustomerWriteSerializer(
            customer, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(CustomerDetailSerializer(customer).data)

    def delete(self, request, customer_id):
        if not request.user.is_admin:
            return Response(
                {"error": "Only administrators can delete customers."},
                status=status.HTTP_403_FORBIDDEN,
            )
        customer = self._get_customer(customer_id, request.user.company)
        if not customer:
            return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)
        name = customer.customer_name
        customer.delete()
        return Response({"message": f"Customer '{name}' deleted."}, status=status.HTTP_200_OK)


class CustomerMovementsView(APIView):
    """
    GET /api/customers/{id}/movements/

    Query params:
        movement_type=<sale|purchase|...>
        date_from=YYYY-MM-DD
        date_to=YYYY-MM-DD
        page=<int>   page_size=<int>
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id):
        try:
            customer = Customer.objects.get(id=customer_id, company=request.user.company)
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)

        from apps.transactions.models import MaterialMovement
        from apps.transactions.serializers import MovementListSerializer

        # Match on FK or raw name (FK takes priority but fallback avoids data loss)
        qs = MaterialMovement.objects.filter(
            company=request.user.company,
            customer=customer,
        ).order_by("-movement_date")

        movement_type = request.query_params.get("movement_type")
        if movement_type:
            qs = qs.filter(movement_type=movement_type)

        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)

        totals = qs.aggregate(
            total_sales=Sum("total_out"),
            total_purchases=Sum("total_in"),
        )

        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, int(request.query_params.get("page_size", 50)))
        total_count = qs.count()
        qs_page = qs[(page - 1) * page_size: page * page_size]

        return Response({
            "customer": {
                "id": str(customer.id),
                "name": customer.customer_name,
                "account_code": customer.account_code,
            },
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "totals": {
                "total_sales": float(totals["total_sales"] or 0),
                "total_purchases": float(totals["total_purchases"] or 0),
            },
            "movements": MovementListSerializer(qs_page, many=True).data,
        })


class CustomerAgingView(APIView):
    """
    GET /api/customers/{id}/aging/
    Returns all aging receivable records for a specific customer.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id):
        try:
            customer = Customer.objects.get(id=customer_id, company=request.user.company)
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)

        from apps.aging.models import AgingReceivable
        from apps.aging.serializers import AgingReceivableSerializer

        records = AgingReceivable.objects.filter(
            company=request.user.company,
            customer=customer,
        ).order_by("-report_date")

        return Response({
            "customer": {
                "id": str(customer.id),
                "name": customer.customer_name,
                "account_code": customer.account_code,
            },
            "aging_records": AgingReceivableSerializer(records, many=True).data,
        })
