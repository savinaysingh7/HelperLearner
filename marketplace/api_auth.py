from django.utils import timezone
from rest_framework import authentication, exceptions

from .models import IntegrationApiKey


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """Authenticate API requests via `X-API-Key` header."""

    header_name = 'HTTP_X_API_KEY'

    def authenticate(self, request):
        raw_key = request.META.get(self.header_name)
        if not raw_key:
            return None

        key_hash = IntegrationApiKey.hash_key(raw_key)
        api_key = (
            IntegrationApiKey.objects.select_related('user')
            .filter(key_hash=key_hash, is_active=True)
            .first()
        )
        if api_key is None:
            raise exceptions.AuthenticationFailed('Invalid API key.')

        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=['last_used_at'])

        if not api_key.user.is_active:
            raise exceptions.AuthenticationFailed('User account is inactive.')
        return api_key.user, None
