"""SIP telephony routes"""

import json
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional, Dict, Any
from urllib.parse import quote

from app.services.livekit import LiveKitClient, get_livekit_client
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/sip-outbound", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def sip_outbound_index(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
    flash_message: Optional[str] = None,
    flash_type: Optional[str] = None,
):
    """SIP outbound calls page"""
    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    trunks = await lk.list_sip_trunks()
    current_user = get_current_user(request)

    return request.app.state.templates.TemplateResponse(
        "sip/outbound.html.j2",
        {
            "request": request,
            "trunks": trunks,
            "current_user": current_user,
            "sip_enabled": lk.sip_enabled,
            "csrf_token": get_csrf_token(request),
            "flash_message": flash_message,
            "flash_type": flash_type,
        },
    )


@router.post("/sip-outbound/create", dependencies=[Depends(requires_admin)])
async def create_sip_call(
    request: Request,
    csrf_token: str = Form(...),
    sip_trunk_id: str = Form(...),
    sip_call_to: str = Form(...),
    room_name: str = Form(...),
    participant_identity: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Create an outbound SIP call"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        await lk.create_sip_participant(
            sip_trunk_id=sip_trunk_id,
            sip_call_to=sip_call_to,
            room_name=room_name,
            participant_identity=participant_identity,
        )
    except Exception as e:
        print(f"Error creating SIP call: {e}")

    return RedirectResponse(url="/sip-outbound", status_code=303)


@router.post("/sip-outbound/trunk/create", dependencies=[Depends(requires_admin)])
async def create_sip_trunk(
    request: Request,
    csrf_token: str = Form(...),
    trunk_name: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    transport: Optional[str] = Form(None),
    numbers: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    destination_country: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    headers: Optional[str] = Form(None),
    headers_to_attributes: Optional[str] = Form(None),
    json_data: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Create a new SIP outbound trunk"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        # Parse numbers if provided
        numbers_list = None
        if numbers:
            numbers_list = [n.strip() for n in numbers.split(",") if n.strip()]

        # Parse JSON fields
        headers_dict = None
        if headers:
            try:
                headers_dict = json.loads(headers)
            except json.JSONDecodeError:
                pass

        headers_to_attrs_dict = None
        if headers_to_attributes:
            try:
                headers_to_attrs_dict = json.loads(headers_to_attributes)
            except json.JSONDecodeError:
                pass

        result = await lk.create_sip_trunk(
            name=trunk_name,
            address=address,
            transport=transport,
            numbers=numbers_list,
            auth_username=username,
            auth_password=password,
            destination_country=destination_country,
            metadata=metadata,
            headers=headers_dict,
            headers_to_attributes=headers_to_attrs_dict,
        )

        # Success message
        trunk_display_name = trunk_name or "Trunk"
        success_msg = quote(f"Successfully created trunk: {trunk_display_name}")
        return RedirectResponse(
            url=f"/sip-outbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        error_msg = str(e)
        print(f"Error creating SIP trunk: {e}")
        import traceback

        traceback.print_exc()

        # Error message
        encoded_error = quote(f"Failed to create trunk: {error_msg}")
        return RedirectResponse(
            url=f"/sip-outbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )


@router.post("/sip-outbound/trunk/update", dependencies=[Depends(requires_admin)])
async def update_sip_trunk(
    request: Request,
    csrf_token: str = Form(...),
    sip_trunk_id: str = Form(...),
    trunk_name: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    transport: Optional[str] = Form(None),
    numbers: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    destination_country: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    headers: Optional[str] = Form(None),
    headers_to_attributes: Optional[str] = Form(None),
    json_data: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Update an existing SIP outbound trunk"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        # Parse numbers if provided
        numbers_list = None
        if numbers:
            numbers_list = [n.strip() for n in numbers.split(",") if n.strip()]

        # Parse JSON fields
        headers_dict = None
        if headers:
            try:
                headers_dict = json.loads(headers)
            except json.JSONDecodeError:
                pass

        headers_to_attrs_dict = None
        if headers_to_attributes:
            try:
                headers_to_attrs_dict = json.loads(headers_to_attributes)
            except json.JSONDecodeError:
                pass

        # Debug logging
        print(f"Updating trunk {sip_trunk_id} with:")
        print(f"  name: {trunk_name}")
        print(f"  address: {address}")
        print(f"  transport: {transport}")
        print(f"  numbers: {numbers_list}")
        print(f"  username: {username}")
        print(f"  destination_country: {destination_country}")
        print(f"  metadata: {metadata}")

        await lk.update_sip_trunk(
            sip_trunk_id=sip_trunk_id,
            name=trunk_name,
            address=address,
            transport=transport,
            numbers=numbers_list,
            auth_username=username,
            auth_password=password if password else None,
            destination_country=destination_country,
            metadata=metadata,
            headers=headers_dict,
            headers_to_attributes=headers_to_attrs_dict,
        )

        # Success message
        trunk_display_name = trunk_name or sip_trunk_id[:16]
        success_msg = quote(f"Successfully updated trunk: {trunk_display_name}")
        return RedirectResponse(
            url=f"/sip-outbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        error_msg = str(e)
        print(f"Error updating SIP trunk: {e}")
        import traceback

        traceback.print_exc()

        # Error message
        encoded_error = quote(f"Failed to update trunk: {error_msg}")
        return RedirectResponse(
            url=f"/sip-outbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )


@router.post("/sip-outbound/trunk/delete", dependencies=[Depends(requires_admin)])
async def delete_sip_trunk(
    request: Request,
    csrf_token: str = Form(...),
    sip_trunk_id: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Delete a SIP outbound trunk"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        await lk.delete_sip_trunk(sip_trunk_id=sip_trunk_id)

        # Success message
        trunk_id_short = sip_trunk_id[:16] if len(sip_trunk_id) > 16 else sip_trunk_id
        success_msg = quote(f"Successfully deleted trunk: {trunk_id_short}...")
        return RedirectResponse(
            url=f"/sip-outbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        error_msg = str(e)
        print(f"Error deleting SIP trunk: {e}")
        import traceback

        traceback.print_exc()

        # Error message
        encoded_error = quote(f"Failed to delete trunk: {error_msg}")
        return RedirectResponse(
            url=f"/sip-outbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )


@router.get("/sip-inbound", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def sip_inbound_index(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
    flash_message: Optional[str] = None,
    flash_type: Optional[str] = None,
):
    """SIP inbound rules page"""
    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    rules = await lk.list_sip_dispatch_rules()
    trunks = await lk.list_sip_inbound_trunks()
    current_user = get_current_user(request)

    return request.app.state.templates.TemplateResponse(
        "sip/inbound.html.j2",
        {
            "request": request,
            "rules": rules,
            "trunks": trunks,
            "current_user": current_user,
            "sip_enabled": lk.sip_enabled,
            "csrf_token": get_csrf_token(request),
            "flash_message": flash_message,
            "flash_type": flash_type,
        },
    )


@router.post("/sip-inbound/trunk/create", dependencies=[Depends(requires_admin)])
async def create_sip_inbound_trunk(
    request: Request,
    csrf_token: str = Form(...),
    trunk_name: Optional[str] = Form(None),
    numbers: Optional[str] = Form(None),
    allowed_addresses: Optional[str] = Form(None),
    allowed_numbers: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Create a new SIP inbound trunk"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        # Parse comma-separated lists
        numbers_list = None
        if numbers:
            numbers_list = [n.strip() for n in numbers.split(",") if n.strip()]

        allowed_addresses_list = None
        if allowed_addresses:
            allowed_addresses_list = [a.strip() for a in allowed_addresses.split(",") if a.strip()]

        allowed_numbers_list = None
        if allowed_numbers:
            allowed_numbers_list = [n.strip() for n in allowed_numbers.split(",") if n.strip()]

        result = await lk.create_sip_inbound_trunk(
            name=trunk_name,
            numbers=numbers_list,
            allowed_addresses=allowed_addresses_list,
            allowed_numbers=allowed_numbers_list,
            auth_username=username,
            auth_password=password,
            metadata=metadata,
        )

        # Success message
        trunk_display_name = trunk_name or "Inbound Trunk"
        success_msg = quote(f"Successfully created inbound trunk: {trunk_display_name}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        error_msg = str(e)
        print(f"Error creating SIP inbound trunk: {e}")
        import traceback
        traceback.print_exc()

        # Error message
        encoded_error = quote(f"Failed to create inbound trunk: {error_msg}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )


@router.post("/sip-inbound/trunk/update", dependencies=[Depends(requires_admin)])
async def update_sip_inbound_trunk(
    request: Request,
    csrf_token: str = Form(...),
    sip_trunk_id: str = Form(...),
    trunk_name: Optional[str] = Form(None),
    numbers: Optional[str] = Form(None),
    allowed_addresses: Optional[str] = Form(None),
    allowed_numbers: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Update an existing SIP inbound trunk"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        # Parse comma-separated lists
        numbers_list = None
        if numbers:
            numbers_list = [n.strip() for n in numbers.split(",") if n.strip()]

        allowed_addresses_list = None
        if allowed_addresses:
            allowed_addresses_list = [a.strip() for a in allowed_addresses.split(",") if a.strip()]

        allowed_numbers_list = None
        if allowed_numbers:
            allowed_numbers_list = [n.strip() for n in allowed_numbers.split(",") if n.strip()]

        await lk.update_sip_inbound_trunk(
            sip_trunk_id=sip_trunk_id,
            name=trunk_name,
            numbers=numbers_list,
            allowed_addresses=allowed_addresses_list,
            allowed_numbers=allowed_numbers_list,
            auth_username=username,
            auth_password=password if password else None,
            metadata=metadata,
        )

        # Success message
        trunk_display_name = trunk_name or sip_trunk_id[:16]
        success_msg = quote(f"Successfully updated inbound trunk: {trunk_display_name}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        error_msg = str(e)
        print(f"Error updating SIP inbound trunk: {e}")
        import traceback
        traceback.print_exc()

        # Error message
        encoded_error = quote(f"Failed to update inbound trunk: {error_msg}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )


@router.post("/sip-inbound/trunk/delete", dependencies=[Depends(requires_admin)])
async def delete_sip_inbound_trunk(
    request: Request,
    csrf_token: str = Form(...),
    sip_trunk_id: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Delete a SIP inbound trunk"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        await lk.delete_sip_trunk(sip_trunk_id=sip_trunk_id)

        # Success message
        trunk_id_short = sip_trunk_id[:16] if len(sip_trunk_id) > 16 else sip_trunk_id
        success_msg = quote(f"Successfully deleted inbound trunk: {trunk_id_short}...")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        error_msg = str(e)
        print(f"Error deleting SIP inbound trunk: {e}")
        import traceback
        traceback.print_exc()

        # Error message
        encoded_error = quote(f"Failed to delete inbound trunk: {error_msg}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )


@router.post("/sip-inbound/rule/create", dependencies=[Depends(requires_admin)])
async def create_dispatch_rule(
    request: Request,
    csrf_token: str = Form(...),
    rule_name: Optional[str] = Form(None),
    trunk_ids: Optional[str] = Form(None),
    dispatch_rule_type: str = Form("direct"),
    room_name: Optional[str] = Form(None),
    room_prefix: Optional[str] = Form(None),
    pin: Optional[str] = Form(None),
    randomize: bool = Form(False),
    hide_phone_number: bool = Form(False),
    agent_name: Optional[str] = Form(None),
    agent_metadata: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    plain_json: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Create a new SIP dispatch rule"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        # Parse trunk IDs
        trunk_ids_list = None
        if trunk_ids:
            trunk_ids_list = [tid.strip() for tid in trunk_ids.split(",") if tid.strip()]

        result = await lk.create_sip_dispatch_rule(
            name=rule_name,
            trunk_ids=trunk_ids_list,
            dispatch_rule_type=dispatch_rule_type,
            room_name=room_name,
            room_prefix=room_prefix,
            pin=pin,
            randomize=randomize,
            hide_phone_number=hide_phone_number,
            agent_name=agent_name,
            agent_metadata=agent_metadata,
            metadata=metadata,
            plain_json=plain_json,
        )

        # Success message
        rule_display_name = rule_name or "Dispatch Rule"
        success_msg = quote(f"Successfully created dispatch rule: {rule_display_name}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        # Extract user-friendly error message
        error_msg = str(e)
        if hasattr(e, 'message'):
            error_msg = e.message
        elif hasattr(e, 'args') and e.args:
            error_msg = str(e.args[0])
        
        print(f"Error creating SIP dispatch rule: {e}")
        import traceback
        traceback.print_exc()

        # Error message - make it more user-friendly
        if "missing rule" in error_msg.lower():
            error_msg = "Invalid dispatch rule configuration. Please check your settings."
        elif "invalid_argument" in error_msg.lower():
            error_msg = "Invalid configuration. Please verify all required fields are filled."
        
        encoded_error = quote(f"Failed to create dispatch rule: {error_msg}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )


@router.post("/sip-inbound/rule/update", dependencies=[Depends(requires_admin)])
async def update_dispatch_rule(
    request: Request,
    csrf_token: str = Form(...),
    sip_dispatch_rule_id: str = Form(...),
    rule_name: Optional[str] = Form(None),
    trunk_ids: Optional[str] = Form(None),
    dispatch_rule_type: Optional[str] = Form(None),
    room_name: Optional[str] = Form(None),
    room_prefix: Optional[str] = Form(None),
    pin: Optional[str] = Form(None),
    randomize: bool = Form(False),
    hide_phone_number: bool = Form(False),
    agent_name: Optional[str] = Form(None),
    agent_metadata: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    plain_json: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Update an existing SIP dispatch rule"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        # Parse trunk IDs
        trunk_ids_list = None
        if trunk_ids:
            trunk_ids_list = [tid.strip() for tid in trunk_ids.split(",") if tid.strip()]

        await lk.update_sip_dispatch_rule(
            sip_dispatch_rule_id=sip_dispatch_rule_id,
            name=rule_name,
            trunk_ids=trunk_ids_list,
            dispatch_rule_type=dispatch_rule_type,
            room_name=room_name,
            room_prefix=room_prefix,
            pin=pin,
            randomize=randomize,
            hide_phone_number=hide_phone_number,
            agent_name=agent_name,
            agent_metadata=agent_metadata,
            metadata=metadata,
            plain_json=plain_json,
        )

        # Success message
        rule_display_name = rule_name or sip_dispatch_rule_id[:16]
        success_msg = quote(f"Successfully updated dispatch rule: {rule_display_name}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        error_msg = str(e)
        print(f"Error updating SIP dispatch rule: {e}")
        import traceback
        traceback.print_exc()

        # Error message
        encoded_error = quote(f"Failed to update dispatch rule: {error_msg}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )


@router.post("/sip-inbound/rule/delete", dependencies=[Depends(requires_admin)])
async def delete_dispatch_rule(
    request: Request,
    csrf_token: str = Form(...),
    sip_dispatch_rule_id: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Delete a SIP dispatch rule"""
    await verify_csrf_token(request)

    if not lk.sip_enabled:
        return RedirectResponse(url="/", status_code=303)

    try:
        await lk.delete_sip_dispatch_rule(sip_dispatch_rule_id=sip_dispatch_rule_id)

        # Success message
        rule_id_short = sip_dispatch_rule_id[:16] if len(sip_dispatch_rule_id) > 16 else sip_dispatch_rule_id
        success_msg = quote(f"Successfully deleted dispatch rule: {rule_id_short}...")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={success_msg}&flash_type=success", status_code=303
        )
    except Exception as e:
        error_msg = str(e)
        print(f"Error deleting SIP dispatch rule: {e}")
        import traceback
        traceback.print_exc()

        # Error message
        encoded_error = quote(f"Failed to delete dispatch rule: {error_msg}")
        return RedirectResponse(
            url=f"/sip-inbound?flash_message={encoded_error}&flash_type=danger", status_code=303
        )
