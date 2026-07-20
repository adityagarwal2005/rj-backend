from rest_framework.pagination import PageNumberPagination

from apps.core.response import api_success


class StandardResultsSetPagination(PageNumberPagination):
    """Default pagination for all list endpoints. ?page=2&page_size=20"""

    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return api_success(
            data={
                "count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
