"""
Tests for GCP service fallbacks and in-memory implementations.

Covers the in-memory Firestore paths (USE_FIRESTORE=false) and
the BigQuery/Pub/Sub fire-and-forget log helpers.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.models.carbon import CarbonResult
from app.models.insights import InsightItem
from app.services import firestore_service


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_result(**kwargs) -> CarbonResult:
    defaults = dict(
        total_kg=5000.0,
        breakdown={"transport": 2500.0, "home": 1000.0, "diet": 1000.0, "consumption": 500.0},
        vs_global_average_pct=125.0,
        vs_paris_target_pct=250.0,
        ranked_categories=[
            {"category": "transport", "kg": 2500.0, "percentage": 50.0},
            {"category": "home", "kg": 1000.0, "percentage": 20.0},
            {"category": "diet", "kg": 1000.0, "percentage": 20.0},
            {"category": "consumption", "kg": 500.0, "percentage": 10.0},
        ],
        device_id="test-device-001",
    )
    defaults.update(kwargs)
    return CarbonResult(**defaults)


def _make_insight(category: str = "transport", priority: int = 1) -> InsightItem:
    return InsightItem(
        category=category,
        action="Take public transport.",
        estimated_saving_kg=800.0,
        timeframe="Achievable within 30 days",
        priority=priority,
    )


# ---------------------------------------------------------------------------
# In-memory Firestore service tests
# ---------------------------------------------------------------------------


class TestInMemoryFirestoreService:
    """Tests for save_entry_memory and get_history_memory."""

    def setup_method(self):
        """Clear the in-memory store before each test."""
        firestore_service._memory_store.clear()

    @pytest.mark.asyncio
    async def test_save_entry_memory_returns_doc_id(self):
        """save_entry_memory must return a non-empty string ID."""
        result = _make_result()
        insights = [_make_insight()]
        doc_id = await firestore_service.save_entry_memory(
            device_id="dev-test-001", result=result, insights=insights
        )
        assert isinstance(doc_id, str)
        assert len(doc_id) > 0

    @pytest.mark.asyncio
    async def test_save_entry_memory_stores_entry(self):
        """Saved entry is retrievable via get_history_memory."""
        result = _make_result(device_id="dev-test-002")
        insights = [_make_insight()]
        doc_id = await firestore_service.save_entry_memory(
            device_id="dev-test-002", result=result, insights=insights
        )
        history = await firestore_service.get_history_memory("dev-test-002")
        assert len(history) == 1
        assert history[0]["id"] == doc_id
        assert history[0]["total_kg"] == 5000.0

    @pytest.mark.asyncio
    async def test_get_history_memory_returns_empty_for_unknown_device(self):
        """Unknown device returns empty list."""
        history = await firestore_service.get_history_memory("unknown-device-999")
        assert history == []

    @pytest.mark.asyncio
    async def test_save_multiple_entries_returned_newest_first(self):
        """Multiple entries are stored newest-first."""
        result1 = _make_result(total_kg=4000.0)
        result2 = _make_result(total_kg=5000.0)
        await firestore_service.save_entry_memory(
            device_id="dev-order-test", result=result1, insights=[]
        )
        await firestore_service.save_entry_memory(
            device_id="dev-order-test", result=result2, insights=[]
        )
        history = await firestore_service.get_history_memory("dev-order-test")
        assert len(history) == 2
        # Most recent entry (result2 = 5000 kg) should be first
        assert history[0]["total_kg"] == 5000.0

    @pytest.mark.asyncio
    async def test_get_history_memory_respects_limit(self):
        """Limit parameter correctly caps returned entries."""
        result = _make_result()
        for _ in range(5):
            await firestore_service.save_entry_memory(
                device_id="dev-limit-test", result=result, insights=[]
            )
        history = await firestore_service.get_history_memory("dev-limit-test", limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_save_entry_memory_includes_insights(self):
        """Saved entry includes serialised insights."""
        result = _make_result()
        insights = [
            _make_insight("transport", 1),
            _make_insight("diet", 2),
            _make_insight("home", 3),
        ]
        await firestore_service.save_entry_memory(
            device_id="dev-insights-test", result=result, insights=insights
        )
        history = await firestore_service.get_history_memory("dev-insights-test")
        assert len(history[0]["insights"]) == 3
        assert history[0]["insights"][0]["category"] == "transport"


# ---------------------------------------------------------------------------
# BigQuery logging tests
# ---------------------------------------------------------------------------


class TestBigQueryLogging:
    """Tests for the fire-and-forget BigQuery log helper."""

    @pytest.mark.asyncio
    async def test_log_event_async_catches_exceptions(self):
        """log_event_async must never raise — it catches all exceptions internally."""
        from app.services import bigquery_service
        from app.core.config import get_settings

        # This will fail to connect to BigQuery (no real GCP credentials)
        # but the function should swallow the error and return None
        result = await bigquery_service.log_event_async(
            total_kg=5000.0,
            diet_type="meat_medium",
            insight_source="rules",
            top_category="transport",
        )
        # Returns None — no exception raised
        assert result is None


# ---------------------------------------------------------------------------
# Pub/Sub service tests
# ---------------------------------------------------------------------------


class TestPubSubService:
    """Tests for the Pub/Sub publish helper."""

    @pytest.mark.asyncio
    async def test_publish_insight_request_catches_exceptions(self):
        """publish_insight_request must never raise — it catches all exceptions internally."""
        from app.services import pubsub_service

        # This will fail without real GCP credentials but should not raise
        result = await pubsub_service.publish_insight_request(
            footprint_total=5000.0,
            top_category="transport",
        )
        assert result is None

