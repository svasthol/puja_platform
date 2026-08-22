"""Import all ORM models so Alembic metadata and mappers see every table."""
from app.models.admin import AdminAuditLog, AdminCredential  # noqa: F401
from app.models.booking import (  # noqa: F401
    Booking,
    BookingAddon,
    BookingAssignment,
    BookingDispatchState,
    BookingStatusHistory,
    SlotHold,
)
from app.models.catalog import (  # noqa: F401
    Puja,
    PujaAddon,
    PujaContentItem,
    PujaMedia,
    Pujari,
    PujariAvailability,
    PujariDocument,
    PujariLiveLocation,
    PujariServiceArea,
    PujariUnavailability,
)
from app.models.engagement import (  # noqa: F401
    ChatConversation,
    ChatMessage,
    Notification,
    PromoCode,
    PromoRedemption,
)
from app.models.identity import (  # noqa: F401
    Address,
    AuthSession,
    OtpVerification,
    User,
    UserRole,
)
from app.models.kyc import KycConsent, KycIdentityRegistry, KycVerificationRequest  # noqa: F401
from app.models.lookups import (  # noqa: F401
    CancellationPolicy,
    PlatformSetting,
    PujaCategory,
    Role,
    ServiceArea,
    StatusType,
)
from app.models.payment import Payment, PaymentSplit, Refund  # noqa: F401
from app.models.relationship_manager import RelationshipManager  # noqa: F401
