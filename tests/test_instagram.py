"""Tests for Meta API request construction, publish order, and failure handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from delivery.instagram import (
    InstagramAPIError,
    InstagramClient,
    InstagramStoryPublisher,
)


@pytest.fixture
def client() -> InstagramClient:
    return InstagramClient(
        account_id="17841400000000000",
        access_token="TEST_TOKEN_SECRET",
        api_version="v21.0",
    )


def test_create_container_request_shape(client: InstagramClient):
    req = client.build_create_container_request("https://cdn.example.com/story1.png")
    assert req["method"] == "POST"
    assert req["url"].endswith("/17841400000000000/media")
    assert req["data"]["media_type"] == "STORIES"
    assert req["data"]["image_url"] == "https://cdn.example.com/story1.png"
    assert "access_token" not in req["data"]


def test_publish_request_shape(client: InstagramClient):
    req = client.build_publish_request("container123")
    assert req["method"] == "POST"
    assert req["url"].endswith("/17841400000000000/media_publish")
    assert req["data"]["creation_id"] == "container123"
    assert "access_token" not in req["data"]


def test_create_story_container_posts_expected_fields(client: InstagramClient):
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"id": "cont_1"}
    session.request.return_value = response
    client.session = session

    container_id = client.create_story_container("https://cdn.example.com/a.png")
    assert container_id == "cont_1"
    kwargs = session.request.call_args.kwargs
    assert kwargs["method"] == "POST"
    assert kwargs["data"]["media_type"] == "STORIES"
    assert kwargs["data"]["image_url"] == "https://cdn.example.com/a.png"
    assert kwargs["data"]["access_token"] == "TEST_TOKEN_SECRET"


def test_token_error_flagged(client: InstagramClient):
    session = MagicMock()
    response = MagicMock()
    response.status_code = 400
    response.json.return_value = {
        "error": {
            "message": "Invalid OAuth access token.",
            "type": "OAuthException",
            "code": 190,
        }
    }
    session.request.return_value = response
    client.session = session

    with pytest.raises(InstagramAPIError) as exc:
        client.create_story_container("https://cdn.example.com/a.png")
    assert exc.value.is_token_error
    assert "TEST_TOKEN_SECRET" not in str(exc.value)


def test_rate_limit_flagged(client: InstagramClient):
    session = MagicMock()
    response = MagicMock()
    response.status_code = 403
    response.json.return_value = {
        "error": {"message": "Application request limit reached", "code": 4}
    }
    session.request.return_value = response
    client.session = session

    with pytest.raises(InstagramAPIError) as exc:
        client.create_story_container("https://cdn.example.com/a.png")
    assert exc.value.is_rate_limit


def test_publish_order_is_sequential(tmp_path: Path):
    paths = [tmp_path / f"story_{i}.png" for i in range(1, 4)]
    for p in paths:
        p.write_bytes(b"png")
    urls = [f"https://cdn.example.com/{p.name}" for p in paths]

    mock_client = MagicMock()
    # Return distinct ids in call order
    mock_client.configured = True
    mock_client.publish_story_image.side_effect = [
        ("c1", "m1"),
        ("c2", "m2"),
        ("c3", "m3"),
    ]

    publisher = InstagramStoryPublisher(client=mock_client)
    publisher.dry_run = False
    publisher.publish_enabled = True

    report = publisher.publish_stories(paths, urls)
    assert report.all_published
    assert [r.media_id for r in report.results] == ["m1", "m2", "m3"]
    called_urls = [c.args[0] for c in mock_client.publish_story_image.call_args_list]
    assert called_urls == urls


def test_story1_failure_stops_sequence(tmp_path: Path):
    paths = [tmp_path / f"story_{i}.png" for i in range(1, 4)]
    for p in paths:
        p.write_bytes(b"png")
    urls = [f"https://cdn.example.com/{p.name}" for p in paths]

    mock_client = MagicMock()
    mock_client.configured = True
    mock_client.publish_story_image.side_effect = InstagramAPIError("boom", error_code=100)

    publisher = InstagramStoryPublisher(client=mock_client)
    publisher.dry_run = False
    publisher.publish_enabled = True

    report = publisher.publish_stories(paths, urls)
    assert report.stopped_early
    assert report.published_count == 0
    assert report.results[0].status == "failed"
    assert report.results[1].status == "skipped"
    assert report.results[2].status == "skipped"
    assert mock_client.publish_story_image.call_count == 1


def test_partial_publication_records_successes(tmp_path: Path):
    paths = [tmp_path / f"story_{i}.png" for i in range(1, 4)]
    for p in paths:
        p.write_bytes(b"png")
    urls = [f"https://cdn.example.com/{p.name}" for p in paths]

    mock_client = MagicMock()
    mock_client.configured = True
    mock_client.publish_story_image.side_effect = [
        ("c1", "m1"),
        InstagramAPIError("later fail", error_code=9007),
    ]

    publisher = InstagramStoryPublisher(client=mock_client)
    publisher.dry_run = False
    publisher.publish_enabled = True

    report = publisher.publish_stories(paths, urls)
    assert report.published_count == 1
    assert report.results[0].status == "published"
    assert report.results[0].media_id == "m1"
    assert report.results[1].status == "failed"
    assert report.results[2].status == "skipped"
    # No automatic repost of story 1
    assert mock_client.publish_story_image.call_count == 2


def test_wait_for_container_finished(client: InstagramClient):
    with patch.object(client, "get_container_status", side_effect=["IN_PROGRESS", "FINISHED"]):
        with patch("delivery.instagram.time.sleep"):
            status = client.wait_for_container("cid", timeout_seconds=10, poll_interval=0)
    assert status == "FINISHED"


def test_dry_run_does_not_call_meta(tmp_path: Path):
    paths = [tmp_path / "story_1.png"]
    paths[0].write_bytes(b"png")
    mock_client = MagicMock()
    mock_client.configured = True

    publisher = InstagramStoryPublisher(client=mock_client)
    publisher.dry_run = True
    publisher.publish_enabled = True

    report = publisher.publish_stories(paths, ["https://cdn.example.com/a.png"])
    assert report.dry_run
    assert report.results[0].status == "dry_run"
    mock_client.publish_story_image.assert_not_called()
