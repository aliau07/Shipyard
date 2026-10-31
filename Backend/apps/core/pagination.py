from rest_framework import pagination


class PageNumberPagination(pagination.PageNumberPagination):
    """20 per page by default; clients may ask for up to 100 with ?page_size=."""

    page_size_query_param = 'page_size'
    max_page_size = 100
