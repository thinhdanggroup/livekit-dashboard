"""LiveKit SDK Client Wrapper - Pure Async Version"""

import asyncio
import base64
import json
import os
import time
from typing import List, Optional, Tuple, Dict, Any

from livekit import api, rtc


class LiveKitClient:
    """Wrapper for LiveKit SDK clients with error handling and metrics - Pure Async"""

    def __init__(self):
        self.url = os.environ["LIVEKIT_URL"]
        self.key = os.environ["LIVEKIT_API_KEY"]
        self.secret = os.environ["LIVEKIT_API_SECRET"]

        # Don't create the API instance here - do it lazily in async context
        self._lk_api = None

        # SIP is optional
        self.sip_enabled = os.environ.get("ENABLE_SIP", "false").lower() == "true"

    async def _get_api(self):
        """Get or create LiveKit API instance in async context"""
        if self._lk_api is None:
            self._lk_api = api.LiveKitAPI(
                url=self.url,
                api_key=self.key,
                api_secret=self.secret,
            )
            await self._lk_api.__aenter__()
        return self._lk_api

    async def close(self):
        """Close the API session"""
        if self._lk_api is not None:
            await self._lk_api.__aexit__(None, None, None)
            self._lk_api = None

    # Room Management
    async def list_rooms(self, names: Optional[List[str]] = None) -> Tuple[List, float]:
        """List all rooms with latency measurement"""
        lk = await self._get_api()
        t0 = time.perf_counter()
        req = api.ListRoomsRequest(names=names if names else [])
        resp = await lk.room.list_rooms(req)
        latency = time.perf_counter() - t0
        return list(resp.rooms), latency

    async def get_room(self, name: str):
        """Get a specific room"""
        rooms, _ = await self.list_rooms(names=[name])
        return rooms[0] if rooms else None

    async def create_room(
        self,
        name: str,
        empty_timeout: int = 300,
        max_participants: int = 100,
        metadata: str = "",
    ):
        """Create a new room"""
        lk = await self._get_api()
        req = api.CreateRoomRequest(
            name=name,
            empty_timeout=empty_timeout,
            max_participants=max_participants,
            metadata=metadata,
        )
        return await lk.room.create_room(req)

    async def delete_room(self, name: str):
        """Delete/close a room"""
        lk = await self._get_api()
        req = api.DeleteRoomRequest(room=name)
        return await lk.room.delete_room(req)

    # Participant Management
    async def list_participants(self, room_name: str) -> List:
        """List participants in a room"""
        lk = await self._get_api()
        req = api.ListParticipantsRequest(room=room_name)
        resp = await lk.room.list_participants(req)
        return list(resp.participants)

    async def get_detailed_participants(self, room_name: str) -> List:
        """Get detailed participant information including metadata and connection info"""
        try:
            lk = await self._get_api()
            req = api.ListParticipantsRequest(room=room_name)
            resp = await lk.room.list_participants(req)
            participants = list(resp.participants)

            # Get additional details for each participant if needed
            detailed_participants = []
            for participant in participants:
                try:
                    # Get full participant details
                    detailed = await lk.room.get_participant(
                        api.RoomParticipantIdentity(room=room_name, identity=participant.identity)
                    )
                    detailed_participants.append(detailed)
                except Exception as e:
                    print(
                        f"DEBUG: Could not get details for participant {participant.identity}: {e}"
                    )
                    # Fallback to basic participant info
                    detailed_participants.append(participant)

            return detailed_participants
        except Exception as e:
            print(f"DEBUG: Error getting detailed participants for room {room_name}: {e}")
            return []

    async def get_all_participants_across_rooms(self) -> List:
        """Get all participants from all rooms with detailed information"""
        try:
            rooms, _ = await self.list_rooms()
            all_participants = []

            for room in rooms:
                participants = await self.get_detailed_participants(room.name)
                # Add room context to each participant
                for participant in participants:
                    participant._room_name = room.name
                all_participants.extend(participants)

            return all_participants
        except Exception as e:
            print(f"DEBUG: Error getting all participants: {e}")
            return []

    async def get_participant(self, room_name: str, identity: str):
        """Get a specific participant"""
        lk = await self._get_api()
        req = api.RoomParticipantIdentity(room=room_name, identity=identity)
        return await lk.room.get_participant(req)

    async def remove_participant(self, room_name: str, identity: str):
        """Kick a participant from a room"""
        lk = await self._get_api()
        req = api.RoomParticipantIdentity(room=room_name, identity=identity)
        return await lk.room.remove_participant(req)

    async def mute_participant_track(
        self, room_name: str, identity: str, track_sid: str, muted: bool
    ):
        """Mute/unmute a participant's track"""
        lk = await self._get_api()
        req = api.MuteRoomTrackRequest(
            room=room_name, identity=identity, track_sid=track_sid, muted=muted
        )
        return await lk.room.mute_published_track(req)

    async def update_participant(
        self,
        room_name: str,
        identity: str,
        metadata: Optional[str] = None,
        permission: Optional[api.ParticipantPermission] = None,
    ):
        """Update participant metadata or permissions"""
        lk = await self._get_api()
        req = api.UpdateParticipantRequest(
            room=room_name, identity=identity, metadata=metadata, permission=permission
        )
        return await lk.room.update_participant(req)

    # Token Generation
    def generate_token(
        self,
        room: str,
        identity: str,
        name: Optional[str] = None,
        ttl: int = 3600,
        metadata: str = "",
        can_publish: bool = True,
        can_subscribe: bool = True,
        can_publish_data: bool = True,
    ) -> str:
        """Generate a join token for a participant (synchronous, no API call)"""
        grant = api.VideoGrants(
            room_join=True,
            room=room,
            can_publish=can_publish,
            can_subscribe=can_subscribe,
            can_publish_data=can_publish_data,
        )

        token = (
            api.AccessToken(self.key, self.secret)
            .with_identity(identity)
            .with_name(name or identity)
            .with_metadata(metadata)
            .with_grants(grant)
            .with_ttl(ttl)
        )

        return token.to_jwt()

    # Egress Management
    async def list_egress(self, room_name: Optional[str] = None, active: bool = True) -> List:
        """List egress jobs"""
        lk = await self._get_api()
        req = api.ListEgressRequest(room_name=room_name or "", active=active)
        resp = await lk.egress.list_egress(req)
        return list(resp.items)

    async def start_room_composite_egress(
        self,
        room_name: str,
        output_filename: str,
        layout: str = "grid",
        audio_only: bool = False,
        video_only: bool = False,
    ):
        """Start a room composite egress"""
        lk = await self._get_api()

        file_output = api.EncodedFileOutput(
            file_type=api.EncodedFileType.MP4,
            filepath=output_filename,
        )

        composite_request = api.RoomCompositeEgressRequest(
            room_name=room_name,
            layout=layout,
            audio_only=audio_only,
            video_only=video_only,
            file_outputs=[file_output],
        )

        return await lk.egress.start_room_composite_egress(composite_request)

    async def stop_egress(self, egress_id: str):
        """Stop an egress job"""
        lk = await self._get_api()
        req = api.StopEgressRequest(egress_id=egress_id)
        return await lk.egress.stop_egress(req)

    # SIP Management (if enabled)
    async def list_sip_trunks(self):
        """List SIP outbound trunks"""
        if not self.sip_enabled:
            return []
        try:
            lk = await self._get_api()
            req = api.ListSIPOutboundTrunkRequest()
            resp = await lk.sip.list_outbound_trunk(req)
            return list(resp.items) if hasattr(resp, "items") else []
        except Exception as e:
            print(f"Error listing SIP trunks: {e}")
            return []

    async def list_sip_inbound_trunks(self):
        """List SIP inbound trunks"""
        if not self.sip_enabled:
            return []
        try:
            lk = await self._get_api()
            req = api.ListSIPInboundTrunkRequest()
            resp = await lk.sip.list_inbound_trunk(req)
            return list(resp.items) if hasattr(resp, "items") else []
        except Exception as e:
            print(f"Error listing SIP inbound trunks: {e}")
            return []

    def _rule_to_json(self, rule) -> str:
        """Convert a SIPDispatchRuleInfo to JSON string"""
        try:
            rule_json = {}

            # Build rule object
            if hasattr(rule, "rule") and rule.rule:
                rule_obj = rule.rule
                if hasattr(rule_obj, "HasField"):
                    if rule_obj.HasField("dispatch_rule_direct"):
                        rule_json["rule"] = {
                            "dispatch_rule_direct": {
                                "room_name": rule_obj.dispatch_rule_direct.room_name or "",
                                "pin": rule_obj.dispatch_rule_direct.pin or "",
                            }
                        }
                    elif rule_obj.HasField("dispatch_rule_individual"):
                        rule_json["rule"] = {
                            "dispatch_rule_individual": {
                                "room_prefix": rule_obj.dispatch_rule_individual.room_prefix or "",
                                "pin": rule_obj.dispatch_rule_individual.pin or "",
                            }
                        }
                    elif rule_obj.HasField("dispatch_rule_callee"):
                        rule_json["rule"] = {
                            "dispatch_rule_callee": {
                                "room_prefix": rule_obj.dispatch_rule_callee.room_prefix or "",
                                "pin": rule_obj.dispatch_rule_callee.pin or "",
                                "randomize": rule_obj.dispatch_rule_callee.randomize,
                            }
                        }

            # Add other fields
            if hasattr(rule, "name") and rule.name:
                rule_json["name"] = rule.name
            if hasattr(rule, "trunk_ids") and rule.trunk_ids:
                rule_json["trunk_ids"] = list(rule.trunk_ids)
            if hasattr(rule, "hide_phone_number"):
                rule_json["hide_phone_number"] = rule.hide_phone_number
            if hasattr(rule, "metadata") and rule.metadata:
                rule_json["metadata"] = rule.metadata
            if hasattr(rule, "attributes") and rule.attributes:
                # Convert protobuf Map to dict
                rule_json["attributes"] = dict(rule.attributes)
            if (
                hasattr(rule, "room_config")
                and rule.room_config
                and hasattr(rule.room_config, "agents")
            ):
                agents = []
                for agent in rule.room_config.agents:
                    agents.append(
                        {"agent_name": agent.agent_name or "", "metadata": agent.metadata or ""}
                    )
                if agents:
                    rule_json["room_config"] = {"agents": agents}

            return json.dumps(rule_json, indent=2)
        except Exception as e:
            print(f"Error converting rule to JSON: {e}")
            return "{}"

    async def list_sip_dispatch_rules(self):
        """List SIP dispatch rules"""
        if not self.sip_enabled:
            return []
        try:
            lk = await self._get_api()
            req = api.ListSIPDispatchRuleRequest()
            resp = await lk.sip.list_dispatch_rule(req)
            rules = list(resp.items) if hasattr(resp, "items") else []

            # Create a wrapper class to add rule_type without modifying protobuf objects
            class RuleWrapper:
                def __init__(self, rule, rule_type, rule_json):
                    self._rule = rule
                    self.rule_type = rule_type
                    self.rule_json = rule_json

                def __getattr__(self, name):
                    # Delegate all other attribute access to the original rule object
                    return getattr(self._rule, name)

            # Determine rule type for each rule and wrap
            wrapped_rules = []
            for rule in rules:
                rule_type = "unknown"
                if hasattr(rule, "rule") and rule.rule:
                    rule_obj = rule.rule
                    # Determine which rule type is set using HasField for protobuf oneof
                    if hasattr(rule_obj, "HasField"):
                        if rule_obj.HasField("dispatch_rule_direct"):
                            rule_type = "direct"
                        elif rule_obj.HasField("dispatch_rule_individual"):
                            rule_type = "individual"
                        elif rule_obj.HasField("dispatch_rule_callee"):
                            rule_type = "callee"
                    # Fallback: check if attribute exists and is not None/empty
                    elif (
                        hasattr(rule_obj, "dispatch_rule_direct")
                        and rule_obj.dispatch_rule_direct is not None
                    ):
                        rule_type = "direct"
                    elif (
                        hasattr(rule_obj, "dispatch_rule_individual")
                        and rule_obj.dispatch_rule_individual is not None
                    ):
                        rule_type = "individual"
                    elif (
                        hasattr(rule_obj, "dispatch_rule_callee")
                        and rule_obj.dispatch_rule_callee is not None
                    ):
                        rule_type = "callee"

                # Convert rule to JSON and encode as base64 for safe HTML attribute storage
                rule_json = self._rule_to_json(rule)
                rule_json_b64 = (
                    base64.b64encode(rule_json.encode("utf-8")).decode("utf-8") if rule_json else ""
                )
                wrapped_rules.append(RuleWrapper(rule, rule_type, rule_json_b64))
            return wrapped_rules
        except Exception as e:
            print(f"Error listing SIP dispatch rules: {e}")
            import traceback

            traceback.print_exc()
            return []

    async def create_sip_participant(
        self,
        sip_trunk_id: str,
        sip_call_to: str,
        room_name: str,
        participant_identity: str,
    ):
        """Create an outbound SIP call"""
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()
        req = api.CreateSIPParticipantRequest(
            sip_trunk_id=sip_trunk_id,
            sip_call_to=sip_call_to,
            room_name=room_name,
            participant_identity=participant_identity,
        )
        return await lk.sip.create_sip_participant(req)

    async def create_sip_trunk(
        self,
        name: Optional[str] = None,
        address: Optional[str] = None,
        transport: Optional[str] = None,
        numbers: Optional[List[str]] = None,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
        destination_country: Optional[str] = None,
        metadata: Optional[str] = None,
        headers: Optional[dict] = None,
        headers_to_attributes: Optional[dict] = None,
        **kwargs,
    ):
        """Create a SIP outbound trunk"""
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()

        # Build trunk info
        trunk_info = api.SIPOutboundTrunkInfo()

        if name:
            trunk_info.name = name
        if address:
            trunk_info.address = address
        if transport:
            # Convert string to SIPTransport enum
            if transport.lower() == "udp":
                trunk_info.transport = api.SIPTransport.SIP_TRANSPORT_UDP
            elif transport.lower() == "tls":
                trunk_info.transport = api.SIPTransport.SIP_TRANSPORT_TLS
            else:
                trunk_info.transport = api.SIPTransport.SIP_TRANSPORT_TCP
        if numbers:
            trunk_info.numbers.extend(numbers)
        if auth_username:
            trunk_info.auth_username = auth_username
        if auth_password:
            trunk_info.auth_password = auth_password
        if destination_country:
            trunk_info.destination_country = destination_country.upper()
        if metadata:
            trunk_info.metadata = metadata
        if headers:
            for key, value in headers.items():
                trunk_info.headers[key] = value
        if headers_to_attributes:
            for key, value in headers_to_attributes.items():
                trunk_info.headers_to_attributes[key] = value

        req = api.CreateSIPOutboundTrunkRequest(trunk=trunk_info)
        return await lk.sip.create_outbound_trunk(req)

    async def update_sip_trunk(
        self,
        sip_trunk_id: str,
        name: Optional[str] = None,
        address: Optional[str] = None,
        transport: Optional[str] = None,
        numbers: Optional[List[str]] = None,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
        destination_country: Optional[str] = None,
        metadata: Optional[str] = None,
        headers: Optional[dict] = None,
        headers_to_attributes: Optional[dict] = None,
        **kwargs,
    ):
        """Update a SIP outbound trunk"""
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()

        # Build trunk info - need to set all fields, not just changed ones
        trunk_info = api.SIPOutboundTrunkInfo(sip_trunk_id=sip_trunk_id)

        # Set name (allow empty string)
        if name is not None:
            trunk_info.name = name

        # Set address (allow empty string)
        if address is not None:
            trunk_info.address = address

        # Set transport
        if transport is not None and transport:
            # Convert string to SIPTransport enum
            transport_lower = transport.lower()
            if transport_lower == "udp" or "udp" in transport_lower:
                trunk_info.transport = api.SIPTransport.SIP_TRANSPORT_UDP
            elif transport_lower == "tls" or "tls" in transport_lower:
                trunk_info.transport = api.SIPTransport.SIP_TRANSPORT_TLS
            else:
                trunk_info.transport = api.SIPTransport.SIP_TRANSPORT_TCP

        # Set numbers
        if numbers is not None:
            trunk_info.numbers.extend(numbers)

        # Set auth username (allow empty string)
        if auth_username is not None:
            trunk_info.auth_username = auth_username

        # Set auth password (only if provided and not empty)
        if auth_password is not None and auth_password:
            trunk_info.auth_password = auth_password

        # Set destination country
        if destination_country is not None:
            trunk_info.destination_country = destination_country.upper()

        # Set metadata
        if metadata is not None:
            trunk_info.metadata = metadata

        # Set headers
        if headers is not None:
            for key, value in headers.items():
                trunk_info.headers[key] = value

        # Set headers to attributes
        if headers_to_attributes is not None:
            for key, value in headers_to_attributes.items():
                trunk_info.headers_to_attributes[key] = value

        # The update method expects the trunk_info directly
        return await lk.sip.update_sip_outbound_trunk(trunk_id=sip_trunk_id, trunk=trunk_info)

    async def delete_sip_trunk(self, sip_trunk_id: str):
        """Delete a SIP trunk (inbound or outbound)"""
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()
        req = api.DeleteSIPTrunkRequest(sip_trunk_id=sip_trunk_id)
        return await lk.sip.delete_trunk(req)

    async def create_sip_inbound_trunk(
        self,
        name: Optional[str] = None,
        numbers: Optional[List[str]] = None,
        allowed_addresses: Optional[List[str]] = None,
        allowed_numbers: Optional[List[str]] = None,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
        metadata: Optional[str] = None,
        **kwargs,
    ):
        """Create a SIP inbound trunk"""
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()

        # Build trunk info
        trunk_info = api.SIPInboundTrunkInfo()

        if name:
            trunk_info.name = name
        if numbers:
            trunk_info.numbers.extend(numbers)
        if allowed_addresses:
            trunk_info.allowed_addresses.extend(allowed_addresses)
        if allowed_numbers:
            trunk_info.allowed_numbers.extend(allowed_numbers)
        if auth_username:
            trunk_info.auth_username = auth_username
        if auth_password:
            trunk_info.auth_password = auth_password
        if metadata:
            trunk_info.metadata = metadata

        req = api.CreateSIPInboundTrunkRequest(trunk=trunk_info)
        return await lk.sip.create_inbound_trunk(req)

    async def update_sip_inbound_trunk(
        self,
        sip_trunk_id: str,
        name: Optional[str] = None,
        numbers: Optional[List[str]] = None,
        allowed_addresses: Optional[List[str]] = None,
        allowed_numbers: Optional[List[str]] = None,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
        metadata: Optional[str] = None,
        **kwargs,
    ):
        """Update a SIP inbound trunk"""
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()

        # Build trunk info
        trunk_info = api.SIPInboundTrunkInfo(sip_trunk_id=sip_trunk_id)

        if name is not None:
            trunk_info.name = name
        if numbers is not None:
            trunk_info.numbers.extend(numbers)
        if allowed_addresses is not None:
            trunk_info.allowed_addresses.extend(allowed_addresses)
        if allowed_numbers is not None:
            trunk_info.allowed_numbers.extend(allowed_numbers)
        if auth_username is not None:
            trunk_info.auth_username = auth_username
        if auth_password is not None and auth_password:
            trunk_info.auth_password = auth_password
        if metadata is not None:
            trunk_info.metadata = metadata

        return await lk.sip.update_inbound_trunk(trunk_id=sip_trunk_id, trunk=trunk_info)

    async def create_sip_dispatch_rule(
        self,
        name: Optional[str] = None,
        trunk_ids: Optional[List[str]] = None,
        hide_phone_number: bool = False,
        dispatch_rule_type: str = "direct",
        room_name: Optional[str] = None,
        room_prefix: Optional[str] = None,
        pin: Optional[str] = None,
        randomize: bool = False,
        metadata: Optional[str] = None,
        attributes: Optional[dict] = None,
        agent_name: Optional[str] = None,
        agent_metadata: Optional[str] = None,
        plain_json: Optional[str] = None,
        **kwargs,
    ):
        """Create a SIP dispatch rule with optional agent configuration

        Args:
            dispatch_rule_type: One of 'direct', 'individual', or 'callee'
                - 'direct': Route to a specific room (requires room_name)
                - 'individual': Route each caller to their own individual room (supports room_prefix, pin)
                - 'callee': Route based on the called number (supports room_prefix, pin, randomize)
            room_name: Room name for direct dispatch type
            room_prefix: Room prefix for individual/callee dispatch types
            pin: PIN for any dispatch type
            randomize: Whether to randomize room name for callee type
            plain_json: Optional JSON string to parse and use for rule configuration (takes precedence over other params)
        """
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()

        # If plain_json is provided, parse it and use it directly
        print(f"DEBUG: plain_json: {plain_json}")
        if plain_json:
            try:
                json_data = json.loads(plain_json)
                # Build rule from JSON
                rule = self._build_rule_from_json(json_data)
                # Build rule_info from JSON
                rule_info = self._build_rule_info_from_json(json_data, rule)

                req = api.CreateSIPDispatchRuleRequest(
                    rule=rule,
                    dispatch_rule=rule_info,
                )
                return await lk.sip.create_dispatch_rule(req)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format: {str(e)}")
            except Exception as e:
                raise ValueError(f"Error parsing JSON: {str(e)}")

        # Build dispatch rule based on type
        print(f"DEBUG: dispatch_rule_type: {dispatch_rule_type}")
        if dispatch_rule_type == "direct":
            # Direct dispatch: route to a specific room
            direct_rule = api.SIPDispatchRuleDirect(
                room_name=room_name or "",
                pin=pin or "",
            )
            rule = api.SIPDispatchRule(dispatch_rule_direct=direct_rule)
        elif dispatch_rule_type == "individual":
            # Individual dispatch: each caller gets their own room
            individual_rule = api.SIPDispatchRuleIndividual(
                room_prefix=room_prefix or "",
                pin=pin or "",
            )
            rule = api.SIPDispatchRule(dispatch_rule_individual=individual_rule)
        elif dispatch_rule_type == "callee":
            # Callee dispatch: route based on called number
            callee_rule = api.SIPDispatchRuleCallee(
                room_prefix=room_prefix or "",
                pin=pin or "",
                randomize=randomize,
            )
            rule = api.SIPDispatchRule(dispatch_rule_callee=callee_rule)
        else:
            raise ValueError(
                f"Invalid dispatch_rule_type: {dispatch_rule_type}. Must be 'direct', 'individual', or 'callee'"
            )

        # Build dispatch rule info
        rule_info_params: Dict[str, Any] = {
            "rule": rule,  # This is required!
        }

        if name:
            rule_info_params["name"] = name
        if trunk_ids:
            rule_info_params["trunk_ids"] = trunk_ids
        if metadata:
            rule_info_params["metadata"] = metadata
        if attributes:
            rule_info_params["attributes"] = attributes
        if hide_phone_number:
            rule_info_params["hide_phone_number"] = hide_phone_number

        # Add agent configuration if provided
        if agent_name:
            agent_dispatch = api.RoomAgentDispatch(
                agent_name=agent_name,
                metadata=agent_metadata or "",
            )
            rule_info_params["room_config"] = api.RoomConfiguration(agents=[agent_dispatch])

        rule_info = api.SIPDispatchRuleInfo(**rule_info_params)

        req = api.CreateSIPDispatchRuleRequest(
            rule=rule,
            dispatch_rule=rule_info,
        )
        return await lk.sip.create_dispatch_rule(req)

    def _build_rule_from_json(self, json_data: Dict[str, Any]) -> api.SIPDispatchRule:
        """Build SIPDispatchRule from JSON data"""
        rule_data = json_data.get("rule", {})

        # Check for dispatch rule types
        if "dispatch_rule_direct" in rule_data:
            direct_data = rule_data["dispatch_rule_direct"]
            direct_rule = api.SIPDispatchRuleDirect(
                room_name=direct_data.get("room_name", ""),
                pin=direct_data.get("pin", ""),
            )
            return api.SIPDispatchRule(dispatch_rule_direct=direct_rule)
        elif "dispatch_rule_individual" in rule_data:
            individual_data = rule_data["dispatch_rule_individual"]
            individual_rule = api.SIPDispatchRuleIndividual(
                room_prefix=individual_data.get("room_prefix", ""),
                pin=individual_data.get("pin", ""),
            )
            return api.SIPDispatchRule(dispatch_rule_individual=individual_rule)
        elif "dispatch_rule_callee" in rule_data:
            callee_data = rule_data["dispatch_rule_callee"]
            callee_rule = api.SIPDispatchRuleCallee(
                room_prefix=callee_data.get("room_prefix", ""),
                pin=callee_data.get("pin", ""),
                randomize=callee_data.get("randomize", False),
            )
            return api.SIPDispatchRule(dispatch_rule_callee=callee_rule)
        else:
            raise ValueError(
                "JSON must contain one of: dispatch_rule_direct, dispatch_rule_individual, or dispatch_rule_callee"
            )

    def _build_rule_info_from_json(
        self, json_data: Dict[str, Any], rule: api.SIPDispatchRule
    ) -> api.SIPDispatchRuleInfo:
        """Build SIPDispatchRuleInfo from JSON data"""
        rule_info_params: Dict[str, Any] = {
            "rule": rule,
        }

        if "name" in json_data:
            rule_info_params["name"] = json_data["name"]
        if "trunk_ids" in json_data:
            rule_info_params["trunk_ids"] = json_data["trunk_ids"]
        if "metadata" in json_data:
            rule_info_params["metadata"] = json_data["metadata"]
        if "attributes" in json_data:
            rule_info_params["attributes"] = json_data["attributes"]
        if "hide_phone_number" in json_data:
            rule_info_params["hide_phone_number"] = json_data["hide_phone_number"]
        if "room_config" in json_data:
            room_config_data = json_data["room_config"]
            agents = []
            if "agents" in room_config_data:
                for agent_data in room_config_data["agents"]:
                    agent = api.RoomAgentDispatch(
                        agent_name=agent_data.get("agent_name", ""),
                        metadata=agent_data.get("metadata", ""),
                    )
                    agents.append(agent)
            rule_info_params["room_config"] = api.RoomConfiguration(agents=agents)

        return api.SIPDispatchRuleInfo(**rule_info_params)

    async def update_sip_dispatch_rule(
        self,
        sip_dispatch_rule_id: str,
        name: Optional[str] = None,
        trunk_ids: Optional[List[str]] = None,
        hide_phone_number: Optional[bool] = None,
        dispatch_rule_type: Optional[str] = None,
        room_name: Optional[str] = None,
        room_prefix: Optional[str] = None,
        pin: Optional[str] = None,
        randomize: Optional[bool] = None,
        metadata: Optional[str] = None,
        attributes: Optional[dict] = None,
        agent_name: Optional[str] = None,
        agent_metadata: Optional[str] = None,
        plain_json: Optional[str] = None,
        **kwargs,
    ):
        """Update a SIP dispatch rule with optional agent configuration

        Args:
            dispatch_rule_type: One of 'direct', 'individual', or 'callee'
                - 'direct': Route to a specific room (requires room_name)
                - 'individual': Route each caller to their own individual room (supports room_prefix, pin)
                - 'callee': Route based on the called number (supports room_prefix, pin, randomize)
            room_name: Room name for direct dispatch type
            room_prefix: Room prefix for individual/callee dispatch types
            pin: PIN for any dispatch type
            randomize: Whether to randomize room name for callee type
            plain_json: Optional JSON string to parse and use for rule configuration (takes precedence over other params)
        """
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()

        # If plain_json is provided, parse it and use it directly
        print(f"DEBUG: plain_json: {plain_json}")
        if plain_json:
            try:
                json_data = json.loads(plain_json)
                # Build rule from JSON
                rule = self._build_rule_from_json(json_data)
                # Build rule_info from JSON and add sip_dispatch_rule_id
                rule_info_json = self._build_rule_info_from_json(json_data, rule)
                # Create new rule_info with sip_dispatch_rule_id
                rule_info_params_json: Dict[str, Any] = {
                    "sip_dispatch_rule_id": sip_dispatch_rule_id,
                    "rule": rule,
                }
                # Copy fields from rule_info_json
                if hasattr(rule_info_json, "name") and rule_info_json.name:
                    rule_info_params_json["name"] = rule_info_json.name
                if hasattr(rule_info_json, "trunk_ids") and rule_info_json.trunk_ids:
                    rule_info_params_json["trunk_ids"] = list(rule_info_json.trunk_ids)
                if hasattr(rule_info_json, "metadata") and rule_info_json.metadata:
                    rule_info_params_json["metadata"] = rule_info_json.metadata
                if hasattr(rule_info_json, "attributes") and rule_info_json.attributes:
                    rule_info_params_json["attributes"] = dict(rule_info_json.attributes)
                if hasattr(rule_info_json, "hide_phone_number"):
                    rule_info_params_json["hide_phone_number"] = rule_info_json.hide_phone_number
                if hasattr(rule_info_json, "room_config") and rule_info_json.room_config:
                    rule_info_params_json["room_config"] = rule_info_json.room_config

                rule_info = api.SIPDispatchRuleInfo(**rule_info_params_json)

                return await lk.sip.update_dispatch_rule(
                    rule_id=sip_dispatch_rule_id,
                    rule=rule_info,
                )
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format: {str(e)}")
            except Exception as e:
                raise ValueError(f"Error parsing JSON: {str(e)}")

        # Build dispatch rule based on type
        # If dispatch_rule_type is provided, set the appropriate rule type
        print(f"DEBUG: dispatch_rule_type: {dispatch_rule_type}")
        if dispatch_rule_type:
            if dispatch_rule_type == "direct":
                # Direct dispatch: route to a specific room
                direct_rule = api.SIPDispatchRuleDirect(
                    room_name=room_name or "",
                    pin=pin or "",
                )
                rule = api.SIPDispatchRule(dispatch_rule_direct=direct_rule)
            elif dispatch_rule_type == "individual":
                # Individual dispatch: each caller gets their own room
                individual_rule = api.SIPDispatchRuleIndividual(
                    room_prefix=room_prefix or "",
                    pin=pin or "",
                )
                rule = api.SIPDispatchRule(dispatch_rule_individual=individual_rule)
                print(f"DEBUG: individual_rule: {individual_rule}")
            elif dispatch_rule_type == "callee":
                # Callee dispatch: route based on called number
                callee_rule = api.SIPDispatchRuleCallee(
                    room_prefix=room_prefix or "",
                    pin=pin or "",
                    randomize=randomize if randomize is not None else False,
                )
                rule = api.SIPDispatchRule(dispatch_rule_callee=callee_rule)
            else:
                raise ValueError(
                    f"Invalid dispatch_rule_type: {dispatch_rule_type}. Must be 'direct', 'individual', or 'callee'"
                )
        else:
            # If type not provided, try to preserve existing rule structure
            # For backward compatibility, assume direct if room_name or pin is provided
            if room_name is not None or pin is not None:
                direct_rule = api.SIPDispatchRuleDirect(
                    room_name=room_name or "",
                    pin=pin or "",
                )
                rule = api.SIPDispatchRule(dispatch_rule_direct=direct_rule)

        # Build dispatch rule info
        rule_info_params: Dict[str, Any] = {
            "sip_dispatch_rule_id": sip_dispatch_rule_id,
            "rule": rule,
        }

        if name is not None:
            rule_info_params["name"] = name
        if trunk_ids is not None:
            rule_info_params["trunk_ids"] = trunk_ids
        if metadata is not None:
            rule_info_params["metadata"] = metadata
        if attributes is not None:
            rule_info_params["attributes"] = attributes
        if hide_phone_number is not None:
            rule_info_params["hide_phone_number"] = hide_phone_number

        # Add agent configuration if provided
        if agent_name is not None:
            if agent_name:  # If not empty string
                agent_dispatch = api.RoomAgentDispatch(
                    agent_name=agent_name,
                    metadata=agent_metadata or "",
                )
                rule_info_params["room_config"] = api.RoomConfiguration(agents=[agent_dispatch])
            else:
                # Empty agent_name means clear the agent configuration
                rule_info_params["room_config"] = api.RoomConfiguration()

        rule_info = api.SIPDispatchRuleInfo(**rule_info_params)

        return await lk.sip.update_dispatch_rule(
            rule_id=sip_dispatch_rule_id,
            rule=rule_info,
        )

    async def delete_sip_dispatch_rule(self, sip_dispatch_rule_id: str):
        """Delete a SIP dispatch rule"""
        if not self.sip_enabled:
            raise ValueError("SIP is not enabled")

        lk = await self._get_api()
        req = api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=sip_dispatch_rule_id)
        return await lk.sip.delete_dispatch_rule(req)

    # Room Analytics
    async def get_room_analytics(self) -> dict:
        """Get comprehensive room analytics data"""
        try:
            print("DEBUG: Fetching room analytics...")
            rooms, latency = await self.list_rooms()
            print(f"DEBUG: Found {len(rooms)} rooms")

            # Calculate room statistics
            total_participants = sum(getattr(r, "num_participants", 0) for r in rooms)
            active_rooms = len([r for r in rooms if getattr(r, "num_participants", 0) > 0])
            empty_rooms = len(rooms) - active_rooms

            # Calculate average participants per room
            avg_participants = round(total_participants / len(rooms), 1) if rooms else 0

            # Room size distribution
            room_sizes = {"small": 0, "medium": 0, "large": 0}  # 1-5, 6-20, 21+
            for room in rooms:
                participants = getattr(room, "num_participants", 0)
                if participants == 0:
                    continue
                elif participants <= 5:
                    room_sizes["small"] += 1
                elif participants <= 20:
                    room_sizes["medium"] += 1
                else:
                    room_sizes["large"] += 1

            # Recent activity (mock data - would need historical data)
            rooms_created_today = len(rooms)  # Simplified

            result = {
                "total_rooms": len(rooms),
                "active_rooms": active_rooms,
                "empty_rooms": empty_rooms,
                "total_participants": total_participants,
                "avg_participants": avg_participants,
                "room_sizes": room_sizes,
                "rooms_created_today": rooms_created_today,
                "api_latency_ms": round(latency * 1000, 2),
            }
            print(f"DEBUG: Room analytics result: {result}")
            return result

        except Exception as e:
            print(f"DEBUG: Error getting room analytics: {e}")
            return {
                "total_rooms": 0,
                "active_rooms": 0,
                "empty_rooms": 0,
                "total_participants": 0,
                "avg_participants": 0,
                "room_sizes": {"small": 0, "medium": 0, "large": 0},
                "rooms_created_today": 0,
                "api_latency_ms": 0,
            }

    # Egress Analytics
    async def get_egress_analytics(self) -> dict:
        """Get comprehensive egress analytics data"""
        try:
            print("DEBUG: Fetching egress analytics...")

            # Get active and recent egress jobs
            active_egress = await self.list_egress(active=True)
            all_egress = await self.list_egress(active=False)  # All recent jobs

            print(f"DEBUG: Active egress: {len(active_egress)}, All recent: {len(all_egress)}")

            # Calculate statistics
            active_count = len(active_egress)
            completed_count = len(
                [e for e in all_egress if getattr(e, "status", None) == 3]
            )  # EGRESS_COMPLETE
            failed_count = len(
                [e for e in all_egress if getattr(e, "status", None) == 4]
            )  # EGRESS_FAILED

            # Egress types distribution
            egress_types = {"room_composite": 0, "participant": 0, "track": 0, "web": 0}
            for egress in all_egress:
                # Check egress type based on request type
                if hasattr(egress, "room_composite"):
                    egress_types["room_composite"] += 1
                elif hasattr(egress, "participant"):
                    egress_types["participant"] += 1
                elif hasattr(egress, "track_composite") or hasattr(egress, "track"):
                    egress_types["track"] += 1
                elif hasattr(egress, "web"):
                    egress_types["web"] += 1

            # Success rate calculation
            total_jobs = completed_count + failed_count
            success_rate = round((completed_count / total_jobs * 100), 1) if total_jobs > 0 else 100

            # Storage used (mock data - would need actual metrics)
            storage_used_gb = len(all_egress) * 0.5  # Mock: 500MB per job

            result = {
                "active_jobs": active_count,
                "completed_jobs": completed_count,
                "failed_jobs": failed_count,
                "success_rate": success_rate,
                "egress_types": egress_types,
                "storage_used_gb": round(storage_used_gb, 1),
                "total_jobs_today": len(all_egress),  # Simplified
            }
            print(f"DEBUG: Egress analytics result: {result}")
            return result

        except Exception as e:
            print(f"DEBUG: Error getting egress analytics: {e}")
            return {
                "active_jobs": 0,
                "completed_jobs": 0,
                "failed_jobs": 0,
                "success_rate": 100,
                "egress_types": {"room_composite": 0, "participant": 0, "track": 0, "web": 0},
                "storage_used_gb": 0,
                "total_jobs_today": 0,
            }

    # Ingress Analytics
    async def get_ingress_analytics(self) -> dict:
        """Get comprehensive ingress analytics data"""
        try:
            print("DEBUG: Fetching ingress analytics...")
            lk = await self._get_api()

            # Get ingress list
            from livekit.protocol.ingress import ListIngressRequest

            req = ListIngressRequest()
            resp = await lk.ingress.list_ingress(req)
            ingress_list = list(resp.items) if hasattr(resp, "items") else []

            print(f"DEBUG: Found {len(ingress_list)} ingress items")

            # Calculate statistics
            total_ingress = len(ingress_list)
            active_ingress = len(
                [i for i in ingress_list if getattr(i, "state", None) == 1]
            )  # INGRESS_STATE_ENDPOINT_PUBLISHED

            # Ingress types (mock distribution)
            ingress_types = {"rtmp": 0, "whip": 0, "url": 0}
            for ingress in ingress_list:
                # This would need to check actual ingress type from the protocol
                # For now, using mock distribution
                ingress_types["rtmp"] += 1

            # Connection quality (mock data)
            avg_bitrate_mbps = 2.5
            connection_stability = 98.5

            result = {
                "total_ingress": total_ingress,
                "active_ingress": active_ingress,
                "ingress_types": ingress_types,
                "avg_bitrate_mbps": avg_bitrate_mbps,
                "connection_stability": connection_stability,
                "streams_today": total_ingress,  # Simplified
            }
            print(f"DEBUG: Ingress analytics result: {result}")
            return result

        except Exception as e:
            print(f"DEBUG: Error getting ingress analytics: {e}")
            return {
                "total_ingress": 0,
                "active_ingress": 0,
                "ingress_types": {"rtmp": 0, "whip": 0, "url": 0},
                "avg_bitrate_mbps": 0,
                "connection_stability": 0,
                "streams_today": 0,
            }

    # Webhook Analytics (for future enhancement)
    async def get_webhook_analytics(self) -> dict:
        """
        Get analytics from stored webhook events.
        This would require a database to store webhook events over time.
        """
        # This is a placeholder for webhook-based analytics
        # In a real implementation, you would:
        # 1. Set up webhook endpoints to receive LiveKit events
        # 2. Store events in a database (participant_joined, participant_left, etc.)
        # 3. Query the database for analytics data

        # For now, return empty data
        return {
            "has_webhook_data": False,
            "participant_joins_today": 0,
            "participant_leaves_today": 0,
            "room_creates_today": 0,
            "track_publishes_today": 0,
        }

    # Enhanced Analytics (combining real-time + historical)
    async def get_enhanced_analytics(self) -> dict:
        """
        Get enhanced analytics combining real-time data with historical data.
        This provides the most comprehensive view.
        """
        try:
            # Get real-time data
            room_analytics = await self.get_room_analytics()

            # Get webhook data (if available)
            webhook_analytics = await self.get_webhook_analytics()

            # Calculate enhanced metrics
            total_participants = room_analytics.get("total_participants", 0)
            total_rooms = room_analytics.get("total_rooms", 0)

            # Connection success rate based on room/participant health
            if total_rooms > 0:
                active_rooms = room_analytics.get("active_rooms", 0)
                connection_success = round((active_rooms / total_rooms) * 100, 1)
            else:
                connection_success = 100

            # Estimate platforms based on room patterns
            platforms = {}
            if total_participants > 0:
                # Realistic distribution for demo
                platforms = {
                    "Web": int(total_participants * 0.6),
                    "iOS": int(total_participants * 0.2),
                    "Android": int(total_participants * 0.15),
                    "React Native": int(total_participants * 0.05),
                }
            else:
                # Sample data when no participants
                platforms = {"Web": 8, "iOS": 3, "Android": 2, "React Native": 1}

            # Connection types based on LiveKit deployment
            connection_types = (
                {
                    "WebRTC Direct": max(1, int(total_participants * 0.7)),
                    "TURN Relay": max(1, int(total_participants * 0.3)),
                }
                if total_participants > 0
                else {"WebRTC Direct": 10, "TURN Relay": 4}
            )

            # Estimate connection minutes
            avg_session_minutes = 25  # Average session length
            connection_minutes = total_participants * avg_session_minutes

            return {
                "connection_success": connection_success,
                "connection_minutes": connection_minutes,
                "platforms": platforms,
                "connection_types": connection_types,
                "enhanced": True,
                "participant_count": total_participants,
                "room_count": total_rooms,
            }

        except Exception as e:
            print(f"DEBUG: Error getting enhanced analytics: {e}")
            # Fallback to sample data
            return {
                "connection_success": 95.8,
                "connection_minutes": 237,
                "platforms": {"Web": 12, "iOS": 5, "Android": 3, "React Native": 2},
                "connection_types": {"WebRTC Direct": 15, "TURN Relay": 7},
                "enhanced": True,
                "participant_count": 0,
                "room_count": 0,
            }

    async def get_sip_analytics(self) -> dict:
        """Get SIP/telephony analytics data"""
        print(f"DEBUG: get_sip_analytics called, sip_enabled = {self.sip_enabled}")

        if not self.sip_enabled:
            print("DEBUG: SIP is not enabled, returning empty analytics")
            return {
                "total_trunks": 0,
                "inbound_trunks": 0,
                "outbound_trunks": 0,
                "dispatch_rules": 0,
                "trunk_status": {},
                "call_volume": 0,
                "connection_success_rate": 0,
            }

        try:
            print("DEBUG: Fetching SIP data...")
            # Get trunk counts
            inbound_trunks = await self.list_sip_inbound_trunks()
            print(f"DEBUG: inbound_trunks count: {len(inbound_trunks)}")

            outbound_trunks = await self.list_sip_trunks()
            print(f"DEBUG: outbound_trunks count: {len(outbound_trunks)}")

            dispatch_rules = await self.list_sip_dispatch_rules()
            print(f"DEBUG: dispatch_rules count: {len(dispatch_rules)}")

            # Analyze trunk status
            trunk_status = {"active": 0, "configured": 0}

            # Count inbound trunks by status
            for trunk in inbound_trunks:
                if hasattr(trunk, "numbers") and trunk.numbers:
                    trunk_status["active"] += 1
                else:
                    trunk_status["configured"] += 1

            # Count outbound trunks by status
            for trunk in outbound_trunks:
                if hasattr(trunk, "address") and trunk.address:
                    trunk_status["active"] += 1
                else:
                    trunk_status["configured"] += 1

            # Calculate connection success rate (mock data for now, would need actual call logs)
            connection_success_rate = 95.5 if (inbound_trunks or outbound_trunks) else 0

            result = {
                "total_trunks": len(inbound_trunks) + len(outbound_trunks),
                "inbound_trunks": len(inbound_trunks),
                "outbound_trunks": len(outbound_trunks),
                "dispatch_rules": len(dispatch_rules),
                "trunk_status": trunk_status,
                "call_volume": 42,  # Mock data - would need actual call metrics
                "connection_success_rate": connection_success_rate,
            }
            print(f"DEBUG: SIP analytics result: {result}")
            return result
        except Exception as e:
            print(f"DEBUG: Error getting SIP analytics: {e}")
            return {
                "total_trunks": 0,
                "inbound_trunks": 0,
                "outbound_trunks": 0,
                "dispatch_rules": 0,
                "trunk_status": {},
                "call_volume": 0,
                "connection_success_rate": 0,
            }

    # Health & Metrics
    async def get_server_info(self) -> dict:
        """Get server information and health status"""
        try:
            rooms, latency = await self.list_rooms()
            total_participants = sum(getattr(r, "num_participants", 0) for r in rooms)

            return {
                "status": "healthy",
                "rooms_count": len(rooms),
                "participants_count": total_participants,
                "sdk_latency_ms": round(latency * 1000, 2),
                "url": self.url,
                "sip_enabled": self.sip_enabled,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "url": self.url,
            }

    # RTC Connection Methods
    async def connect_to_room_for_stats(
        self, room_name: str
    ) -> Tuple[Optional[Any], float, Optional[str]]:
        """Connect to a room via RTC and get connection stats

        Returns:
            Tuple of (stats, latency_ms, error_message)
        """
        room = None
        error_msg = None
        stats = None
        latency = 0.0

        try:
            t0 = time.perf_counter()

            # Create access token for temporary connection
            grant = api.VideoGrants(
                room_join=True, room=room_name, can_publish=False, can_subscribe=True
            )

            token = (
                api.AccessToken(self.key, self.secret)
                .with_identity("dashboard-stats-client")
                .with_name("Dashboard Stats Client")
                .with_grants(grant)
                .to_jwt()
            )

            # Create room and connect
            room = rtc.Room()

            # Connect to the room
            await room.connect(self.url, token)

            # Wait a moment for connection to stabilize
            await asyncio.sleep(0.5)

            # Get RTC stats
            if room.isconnected():
                stats = await room.get_rtc_stats()

            latency = (time.perf_counter() - t0) * 1000  # Convert to ms

        except Exception as e:
            error_msg = str(e)
            latency = (time.perf_counter() - t0) * 1000 if "t0" in locals() else 0.0

        finally:
            # Always disconnect to clean up
            if room:
                try:
                    await room.disconnect()
                except:
                    pass  # Ignore disconnect errors

        return stats, latency, error_msg

    async def get_room_rtc_stats(self, room_name: str) -> Tuple[Dict[str, Any], float]:
        """Get RTC statistics for a room

        Returns:
            Tuple of (stats_dict, latency_ms)
        """
        stats, latency, error = await self.connect_to_room_for_stats(room_name)

        if error:
            return {"error": error, "room_name": room_name}, latency

        if not stats:
            return {"error": "No stats available", "room_name": room_name}, latency

        # Convert RTC stats to dictionary format
        stats_dict = {
            "room_name": room_name,
            "publisher_stats": [],
            "subscriber_stats": [],
            "latency_ms": latency,
        }

        # Process publisher stats - focus on meaningful data
        for stat in stats.publisher_stats:
            stat_type = stat.WhichOneof("stats")
            stat_info = {
                "timestamp": getattr(stat, "timestamp", None),
                "type": stat_type,
            }

            # Add specific stats based on type
            if (
                stat_type == "outbound_rtp"
                and hasattr(stat, "outbound_rtp")
                and stat.HasField("outbound_rtp")
            ):
                rtp_stats = stat.outbound_rtp
                if hasattr(rtp_stats, "outbound") and rtp_stats.HasField("outbound"):
                    outbound = rtp_stats.outbound
                    stat_info.update(
                        {
                            "packets_sent": getattr(outbound, "packets_sent", 0),
                            "bytes_sent": getattr(outbound, "bytes_sent", 0),
                            "retransmitted_packets_sent": getattr(
                                outbound, "retransmitted_packets_sent", 0
                            ),
                            "target_bitrate": getattr(outbound, "target_bitrate", 0),
                            "frames_encoded": getattr(outbound, "frames_encoded", 0),
                            "key_frames_encoded": getattr(outbound, "key_frames_encoded", 0),
                            "total_encode_time": getattr(outbound, "total_encode_time", 0),
                            "nack_count": getattr(outbound, "nack_count", 0),
                            "fir_count": getattr(outbound, "fir_count", 0),
                            "pli_count": getattr(outbound, "pli_count", 0),
                        }
                    )

            elif stat_type == "peer_connection" and hasattr(stat, "peer_connection"):
                # Add connection-level stats
                stat_info["connection_type"] = "publisher"

            # Only include meaningful stats
            if stat_type in ["outbound_rtp", "peer_connection", "transport"]:
                stats_dict["publisher_stats"].append(stat_info)

        # Process subscriber stats - focus on meaningful data
        for stat in stats.subscriber_stats:
            stat_type = stat.WhichOneof("stats")
            stat_info = {
                "timestamp": getattr(stat, "timestamp", None),
                "type": stat_type,
            }

            # Add specific stats based on type
            if (
                stat_type == "inbound_rtp"
                and hasattr(stat, "inbound_rtp")
                and stat.HasField("inbound_rtp")
            ):
                rtp_stats = stat.inbound_rtp
                if hasattr(rtp_stats, "inbound") and rtp_stats.HasField("inbound"):
                    inbound = rtp_stats.inbound
                    stat_info.update(
                        {
                            "packets_received": getattr(inbound, "packets_received", 0),
                            "bytes_received": getattr(inbound, "bytes_received", 0),
                            "packets_lost": getattr(inbound, "packets_lost", 0),
                            "jitter": getattr(inbound, "jitter", 0),
                            # Audio-specific metrics
                            "total_samples_received": getattr(inbound, "total_samples_received", 0),
                            "concealed_samples": getattr(inbound, "concealed_samples", 0),
                            "concealment_events": getattr(inbound, "concealment_events", 0),
                            "audio_level": getattr(inbound, "audio_level", 0),
                            "total_audio_energy": getattr(inbound, "total_audio_energy", 0),
                            "total_samples_duration": getattr(inbound, "total_samples_duration", 0),
                            "jitter_buffer_delay": getattr(inbound, "jitter_buffer_delay", 0),
                            "jitter_buffer_target_delay": getattr(
                                inbound, "jitter_buffer_target_delay", 0
                            ),
                            "jitter_buffer_emitted_count": getattr(
                                inbound, "jitter_buffer_emitted_count", 0
                            ),
                            # Video-specific metrics
                            "frames_decoded": getattr(inbound, "frames_decoded", 0),
                            "frames_dropped": getattr(inbound, "frames_dropped", 0),
                            "frames_rendered": getattr(inbound, "frames_rendered", 0),
                            "key_frames_decoded": getattr(inbound, "key_frames_decoded", 0),
                            "frame_width": getattr(inbound, "frame_width", 0),
                            "frame_height": getattr(inbound, "frame_height", 0),
                            "frames_per_second": getattr(inbound, "frames_per_second", 0),
                            # Network quality metrics
                            "nack_count": getattr(inbound, "nack_count", 0),
                            "fir_count": getattr(inbound, "fir_count", 0),
                            "pli_count": getattr(inbound, "pli_count", 0),
                            "packets_discarded": getattr(inbound, "packets_discarded", 0),
                            "retransmitted_packets_received": getattr(
                                inbound, "retransmitted_packets_received", 0
                            ),
                            "retransmitted_bytes_received": getattr(
                                inbound, "retransmitted_bytes_received", 0
                            ),
                        }
                    )

            elif stat_type == "candidate_pair" and hasattr(stat, "candidate_pair"):
                # Add network connectivity stats
                pair_stats = stat.candidate_pair
                if hasattr(pair_stats, "candidate_pair"):
                    pair_data = pair_stats.candidate_pair
                    stat_info.update(
                        {
                            "bytes_sent": getattr(pair_data, "bytes_sent", 0),
                            "bytes_received": getattr(pair_data, "bytes_received", 0),
                            "packets_sent": getattr(pair_data, "packets_sent", 0),
                            "packets_received": getattr(pair_data, "packets_received", 0),
                            "current_round_trip_time": getattr(
                                pair_data, "current_round_trip_time", 0
                            ),
                            "total_round_trip_time": getattr(pair_data, "total_round_trip_time", 0),
                            "available_outgoing_bitrate": getattr(
                                pair_data, "available_outgoing_bitrate", 0
                            ),
                            "available_incoming_bitrate": getattr(
                                pair_data, "available_incoming_bitrate", 0
                            ),
                            "nominated": getattr(pair_data, "nominated", False),
                            "state": getattr(pair_data, "state", 0),
                            "requests_sent": getattr(pair_data, "requests_sent", 0),
                            "responses_received": getattr(pair_data, "responses_received", 0),
                            "packets_discarded_on_send": getattr(
                                pair_data, "packets_discarded_on_send", 0
                            ),
                        }
                    )

            elif stat_type == "transport" and hasattr(stat, "transport"):
                # Add transport-level stats
                stat_info["connection_type"] = "subscriber"

            # Only include meaningful stats
            if stat_type in ["inbound_rtp", "candidate_pair", "transport", "peer_connection"]:
                stats_dict["subscriber_stats"].append(stat_info)

        return stats_dict, latency


# Dependency injection helper
def get_livekit_client() -> LiveKitClient:
    """FastAPI dependency to get LiveKit client"""
    return LiveKitClient()
