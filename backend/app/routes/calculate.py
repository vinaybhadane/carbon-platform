"""
POST /api/calculate — Calculate annual carbon footprint.

Accepts validated lifestyle inputs, delegates to the pure carbon calculator,
and returns structured results with category breakdown and benchmark comparisons.
"""


from fastapi import APIRouter, Request

from app.carbon.calculator import calculate_footprint
from app.core.rate_limit import CALCULATE_LIMIT, limiter
from app.models.carbon import CarbonInput, CarbonResult

router = APIRouter(tags=["Carbon"])


@router.post(
    "/calculate",
    response_model=CarbonResult,
    summary="Calculate carbon footprint",
    description=(
        "Calculate annual carbon footprint from lifestyle inputs. "
        "Returns total kg CO2e, per-category breakdown, and comparison to global/Paris targets."
    ),
)
@limiter.limit(CALCULATE_LIMIT)
async def calculate_carbon(request: Request, inputs: CarbonInput) -> CarbonResult:
    """
    Calculate annual carbon footprint.

    Rate limited to 30 requests/minute per IP.
    """
    result = calculate_footprint(inputs.model_dump())
    return CarbonResult(**result, device_id=inputs.device_id)
