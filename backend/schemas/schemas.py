"""
Compatibility re-exports. Prefer importing from schemas.<domain> directly.
"""
from schemas.accounts import (  # noqa: F401
    AccountRegisterRequest,
    AccountResponse,
    TransferLotsRequest,
    TransferLotsResponse,
)
from schemas.corporate_actions import (  # noqa: F401
    StockSplitApplyResponse,
    StockSplitCreate,
    StockSplitImpact,
    StockSplitPreviewResponse,
    StockSplitResponse,
)
from schemas.portfolio import (  # noqa: F401
    AggregatePositionCreate,
    AggregatePositionResponse,
    AggregatePositionUploadRequest,
    AggregatePositionUploadResponse,
    AggregatedPositionResponse,
    LotCreate,
    LotResponse,
    LotUploadRequest,
    LotUploadResponse,
)
