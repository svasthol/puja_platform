"""Import all ORM models so Alembic metadata and mappers see every table."""
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
    Pujari,
    PujariAvailability,
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
)
from app.models.lookups import (  # noqa: F401
    CancellationPolicy,
    PlatformSetting,
    PujaCategory,
    Role,
    ServiceArea,
    StatusType,
)
from app.models.payment import Payment, PaymentSplit, Refund  # noqa: F401
