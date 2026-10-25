"""Create real rooms with real simulated participants on the LiveKit server
configured in .env, for recording the README demo video (and for anyone who
wants to click through the dashboard against live-looking data without a
real meeting in progress).

Publishes genuine audio/video tracks over WebRTC via the LiveKit Python
`rtc` client, so Room detail's participant list, track badges, and RTC
connection stats are all real -- nothing in this module touches the
dashboard's own code or data layer.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from livekit import api, rtc

logger = logging.getLogger("demo.live_rooms")


def make_token(key: str, secret: str, room: str, identity: str, name: Optional[str] = None) -> str:
    grant = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True)
    return (
        api.AccessToken(key, secret)
        .with_identity(identity)
        .with_name(name or identity)
        .with_grants(grant)
        .to_jwt()
    )


async def _feed_silence(source: rtc.AudioSource) -> None:
    frame = rtc.AudioFrame.create(48000, 1, 480)
    arr = np.frombuffer(frame.data, dtype=np.int16)
    arr[:] = 0
    while True:
        await source.capture_frame(frame)
        await asyncio.sleep(0.01)


async def _feed_color(source: rtc.VideoSource, width: int, height: int, rgba) -> None:
    buf = bytearray(width * height * 4)
    buf[0::4] = bytes([rgba[0]]) * (width * height)
    buf[1::4] = bytes([rgba[1]]) * (width * height)
    buf[2::4] = bytes([rgba[2]]) * (width * height)
    buf[3::4] = bytes([255]) * (width * height)
    frame = rtc.VideoFrame(width, height, rtc.VideoBufferType.RGBA, bytes(buf))
    while True:
        source.capture_frame(frame)
        await asyncio.sleep(1 / 15)


@dataclass
class LiveParticipant:
    room: rtc.Room
    tasks: List[asyncio.Task] = field(default_factory=list)

    async def disconnect(self) -> None:
        for t in self.tasks:
            t.cancel()
        await self.room.disconnect()


async def connect_participant(
    url: str,
    key: str,
    secret: str,
    room_name: str,
    identity: str,
    display_name: str,
    publish_video: bool = False,
    video_rgba=(60, 110, 220),
) -> LiveParticipant:
    room = rtc.Room()
    token = make_token(key, secret, room_name, identity, display_name)
    await room.connect(url, token, options=rtc.RoomOptions(auto_subscribe=True))

    live = LiveParticipant(room=room)

    audio_source = rtc.AudioSource(sample_rate=48000, num_channels=1)
    audio_track = rtc.LocalAudioTrack.create_audio_track("mic", audio_source)
    await room.local_participant.publish_track(
        audio_track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )
    live.tasks.append(asyncio.create_task(_feed_silence(audio_source)))

    if publish_video:
        video_source = rtc.VideoSource(640, 360)
        video_track = rtc.LocalVideoTrack.create_video_track("camera", video_source)
        await room.local_participant.publish_track(
            video_track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)
        )
        live.tasks.append(asyncio.create_task(_feed_color(video_source, 640, 360, video_rgba)))

    logger.info("connected participant %s to room %s", identity, room_name)
    return live


@dataclass
class DemoSession:
    """Holds every live connection + the LiveKitAPI client, for cleanup."""

    lk: api.LiveKitAPI
    live_participants: List[LiveParticipant] = field(default_factory=list)
    room_names: List[str] = field(default_factory=list)

    async def cleanup(self, delete_rooms: bool = True) -> None:
        for lp in self.live_participants:
            try:
                await lp.disconnect()
            except Exception:
                logger.warning("error disconnecting a demo participant", exc_info=True)
        if delete_rooms:
            for name in self.room_names:
                try:
                    await self.lk.room.delete_room(api.DeleteRoomRequest(room=name))
                except Exception:
                    logger.warning("error deleting demo room %s", name, exc_info=True)
        await self.lk.aclose()


async def build_demo_session(url: str, key: str, secret: str) -> DemoSession:
    """Create the long-lived demo rooms (support-standup, customer-onboarding-42,
    webinar-launch-q4) and run the short design-review join/leave lifecycle so
    the dashboard's background poller records real history for it. Returns
    once the long-lived rooms are live; design-review's departure happens on
    its own timer in the background.
    """
    lk = api.LiveKitAPI(url=url, api_key=key, api_secret=secret)
    session = DemoSession(lk=lk)

    async def _create_room(name: str, empty_timeout: int, metadata: str = "") -> None:
        await lk.room.create_room(
            api.CreateRoomRequest(name=name, empty_timeout=empty_timeout, metadata=metadata)
        )
        session.room_names.append(name)

    # --- Long-lived rooms, stay connected until cleanup() ---
    await _create_room("support-standup", empty_timeout=600)
    session.live_participants.append(
        await connect_participant(url, key, secret, "support-standup", "alice", "Alice Nguyen", publish_video=True, video_rgba=(60, 150, 90))
    )
    session.live_participants.append(
        await connect_participant(url, key, secret, "support-standup", "bao", "Bao Tran")
    )
    session.live_participants.append(
        await connect_participant(url, key, secret, "support-standup", "chi", "Chi Le")
    )

    await _create_room("customer-onboarding-42", empty_timeout=600, metadata='{"account":"acme-corp","plan":"enterprise"}')
    session.live_participants.append(
        await connect_participant(url, key, secret, "customer-onboarding-42", "agent-sales", "Dao (Sales)", publish_video=True, video_rgba=(200, 120, 40))
    )
    session.live_participants.append(
        await connect_participant(url, key, secret, "customer-onboarding-42", "cust-acme", "ACME Guest")
    )

    await _create_room("webinar-launch-q4", empty_timeout=600, metadata='{"topic":"Q4 product launch"}')
    session.live_participants.append(
        await connect_participant(url, key, secret, "webinar-launch-q4", "host-mai", "Mai (Host)", publish_video=True, video_rgba=(170, 60, 170))
    )
    for i in range(1, 4):
        session.live_participants.append(
            await connect_participant(url, key, secret, "webinar-launch-q4", f"viewer-0{i}", f"Viewer 0{i}")
        )

    # --- Short-lived room: full create -> join -> leave cycle for the
    # Session Summary tour. empty_timeout is short so it closes promptly.
    await _create_room("design-review", empty_timeout=12)

    async def _design_review_lifecycle() -> None:
        p1 = await connect_participant(url, key, secret, "design-review", "priya", "Priya Shah")
        p2 = await connect_participant(url, key, secret, "design-review", "minh", "Minh Vu")
        await asyncio.sleep(15)
        await p1.disconnect()
        await asyncio.sleep(2)
        await p2.disconnect()

    asyncio.create_task(_design_review_lifecycle())

    # One real agent dispatch so the Agents fleet page has a real (pending,
    # since no worker is registered) dispatch to show.
    try:
        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="demo-transcriber", room="support-standup", metadata=""
            )
        )
    except Exception:
        logger.warning("could not create demo agent dispatch", exc_info=True)

    return session
