class AppError(Exception):
    code = "INTERNAL_ERROR"
    message = "An unexpected error occurred."
    status_code = 500


class InvalidIPError(AppError):
    code = "INVALID_IP"
    message = "The supplied value is not a valid IP address."
    status_code = 422


class NonPublicIPError(AppError):
    code = "NON_PUBLIC_IP"
    message = "Country lookup is supported only for public IP addresses."
    status_code = 422


class DatabaseUnavailableError(AppError):
    code = "DATABASE_UNAVAILABLE"
    message = "The database is temporarily unavailable."
    status_code = 503


class DatabaseSchemaUnavailableError(AppError):
    code = "DATABASE_SCHEMA_UNAVAILABLE"
    message = "The required database schema is unavailable."
    status_code = 503


class ProviderTimeoutError(AppError):
    code = "PROVIDER_TIMEOUT"
    message = "The country provider timed out."
    status_code = 504


class ProviderAuthenticationError(AppError):
    code = "PROVIDER_AUTHENTICATION_FAILED"
    message = "The country provider rejected authentication."
    status_code = 503


class ProviderRateLimitedError(AppError):
    code = "PROVIDER_RATE_LIMITED"
    message = "The country provider rate limit was reached."
    status_code = 503


class ProviderInvalidResponseError(AppError):
    code = "PROVIDER_INVALID_RESPONSE"
    message = "The country provider returned an unusable response."
    status_code = 502


class ProviderUnavailableError(AppError):
    code = "PROVIDER_UNAVAILABLE"
    message = "The country provider is temporarily unavailable."
    status_code = 503
