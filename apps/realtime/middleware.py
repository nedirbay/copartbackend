from .events import buffered


class RealtimeEventsMiddleware:
    """Bir HTTP soragynyň dowamynda döreýän wakalary jemläp, jogapdan soň bir gezek ugradýar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with buffered():
            return self.get_response(request)
