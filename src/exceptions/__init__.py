class IntegrationError(Exception):
    """Expected, user-displayable integration failure."""


class UnsupportedFileType(IntegrationError):
    pass


class PayloadMissing(IntegrationError):
    pass


class WrongStartLocation(IntegrationError):
    """Only raise when recovery positively identifies a location failure."""


class ServiceUnavailable(IntegrationError):
    pass
