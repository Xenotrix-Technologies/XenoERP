import json
import os
import urllib.request
import urllib.parse
from django.conf import settings


def normalize_phone_number(raw_phone):
    """
    Normalizes phone numbers to standard WhatsApp E.164 numerical format without '+' prefix.
    Handles Indian numbers (9539251789 -> 919539251789, +91 95392 51789 -> 919539251789)
    and international numbers with country codes.
    """
    if not raw_phone:
        return ""
    
    cleaned = ''.join(c for c in str(raw_phone) if c.isdigit())
    if not cleaned:
        return ""

    if str(raw_phone).strip().startswith('+'):
        return cleaned
    
    # 10-digit Indian mobile number
    if len(cleaned) == 10 and cleaned[0] in '6789':
        return '91' + cleaned
    # 11-digit starting with 0 (e.g. 09539251789)
    elif len(cleaned) == 11 and cleaned.startswith('0'):
        return '91' + cleaned[1:]
    
    return cleaned


def get_whatsapp_api_status():
    """
    Returns WhatsApp Business Cloud API configuration and connection status.
    Strictly reads credentials from server-side settings/.env without exposing tokens to frontend.
    """
    token = getattr(settings, 'WHATSAPP_CLOUD_API_TOKEN', '') or os.environ.get('WHATSAPP_CLOUD_API_TOKEN', '')
    phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '') or os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '1249495338254585')
    business_account_id = getattr(settings, 'WHATSAPP_BUSINESS_ACCOUNT_ID', '') or os.environ.get('WHATSAPP_BUSINESS_ACCOUNT_ID', '1753452545807653')

    is_configured = bool(token and token.strip() and phone_number_id and str(phone_number_id).strip())
    
    return {
        'is_connected': is_configured,
        'status_label': 'WhatsApp API Connected' if is_configured else 'WhatsApp API Standby / Unconfigured',
        'business_number': '+91 9995544316',
        'phone_number_id': str(phone_number_id),
        'business_account_id': str(business_account_id),
        'has_token': bool(token),
        'api_version': 'v18.0'
    }


def send_meta_cloud_api_message(
    lead=None,
    recipient_phone=None,
    message_text="",
    buttons=None,
    template_name=None,
    template_language='en_US',
    template_components=None,
    custom_token=None,
    custom_phone_id=None,
    user=None,
    organization=None
):
    """
    Dispatches Meta WhatsApp Business Cloud API messages.
    Supports:
    - Pre-approved Meta WhatsApp Templates (e.g. 'hello_world' or custom business templates)
    - Interactive Reply Buttons (max 3 buttons, max 20 chars per button title)
    - Standard Text Messages (with rich markdown formatting)
    Saves message records to the database and logs timeline Activity on the lead.
    """
    from activities.models import WhatsAppMessage, Activity

    # Determine recipient phone number
    raw_phone = recipient_phone or (lead.phone_number if lead else '')
    cleaned_phone = normalize_phone_number(raw_phone)
    if not cleaned_phone:
        return {
            'success': False,
            'error': 'Recipient phone number is missing or invalid for WhatsApp messaging.'
        }

    # Determine Organization
    org = organization
    if not org and lead:
        org = getattr(lead, 'organization', None)
    if not org and user and hasattr(user, 'profile'):
        org = user.profile.organization

    token = custom_token or getattr(settings, 'WHATSAPP_CLOUD_API_TOKEN', '') or os.environ.get('WHATSAPP_CLOUD_API_TOKEN', '')
    phone_number_id = custom_phone_id or getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '') or os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '1249495338254585')

    if not token or not token.strip():
        return {
            'success': False,
            'error': 'Meta WhatsApp Cloud API Access Token is not configured. Please configure WHATSAPP_CLOUD_API_TOKEN.'
        }

    buttons = buttons or []
    interactive_buttons = []
    
    for idx, b in enumerate(buttons[:3]):
        raw_label = (b.get('text') or b.get('title') or f"Action {idx+1}").strip()
        btn_type = b.get('type', 'Quick Reply')
        btn_id = str(b.get('id') or f"btn_{idx+1}")[:256]
        
        if btn_type == 'Open URL':
            title = f"🔗 {raw_label}"[:20]
        elif btn_type == 'Call Phone':
            title = f"📞 {raw_label}"[:20]
        else:
            title = raw_label[:20]

        interactive_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn_id,
                "title": title
            }
        })

    # Construct Meta WhatsApp Business Cloud API JSON payload
    if template_name and str(template_name).strip():
        t_payload = {
            "name": str(template_name).strip(),
            "language": {
                "code": template_language or "en_US"
            }
        }
        if template_components and isinstance(template_components, list):
            t_payload["components"] = template_components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cleaned_phone,
            "type": "template",
            "template": t_payload
        }
    elif interactive_buttons:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cleaned_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": message_text or "Please choose an option below:"
                },
                "action": {
                    "buttons": interactive_buttons
                }
            }
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cleaned_phone,
            "type": "text",
            "text": {
                "preview_url": True,
                "body": message_text
            }
        }

    meta_api_sent = False
    meta_message_id = None
    api_response = None
    error_msg = None

    graph_url = f"https://graph.facebook.com/v18.0/{str(phone_number_id).strip()}/messages"
    try:
        req_data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            graph_url,
            data=req_data,
            headers={
                'Authorization': f'Bearer {token.strip()}',
                'Content-Type': 'application/json',
                'User-Agent': 'XenoERP-WhatsApp/1.0'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_bytes = resp.read()
            api_response = json.loads(resp_bytes.decode('utf-8'))
            meta_api_sent = True
            
            # Extract Meta Message ID (wamid)
            if api_response.get('messages') and len(api_response['messages']) > 0:
                meta_message_id = api_response['messages'][0].get('id')
    except urllib.error.HTTPError as http_err:
        try:
            err_body = http_err.read().decode('utf-8')
            api_response = json.loads(err_body)
        except Exception:
            api_response = {'error': f"HTTP {http_err.code}: {http_err.reason}"}
    except Exception as err:
        api_response = {'error': str(err)}

    # Parse detailed error message if Meta request failed
    if api_response and 'error' in api_response:
        err_obj = api_response['error']
        if isinstance(err_obj, dict):
            raw_err = err_obj.get('message', 'Meta API request failed')
            err_code = err_obj.get('code')
            err_data = err_obj.get('error_data', {})
            details = err_data.get('details') if isinstance(err_data, dict) else None
        else:
            raw_err = str(err_obj)
            err_code = None
            details = None
        
        user_hint = ""
        if err_code == 131047:
            user_hint = "\n\n💡 Reason: 24-Hour Customer Care Window expired. Meta requires an approved template message (e.g., 'hello_world') to initiate conversation, or send directly via WhatsApp Web/App."
        elif err_code == 131026:
            user_hint = "\n\n💡 Reason: Message undeliverable. Ensure the phone number is active on WhatsApp."
        elif err_code == 190:
            user_hint = "\n\n💡 Reason: Access token expired or invalid. Update WHATSAPP_CLOUD_API_TOKEN in your settings."
        elif err_code == 100:
            if "test" in raw_err.lower() or "recipient" in raw_err.lower():
                user_hint = "\n\n💡 Reason: If using Meta Sandbox / Development credentials, the recipient number must be added under 'To' test numbers in the Meta Developer Console."
            elif "title" in raw_err.lower() or "button" in raw_err.lower():
                user_hint = "\n\n💡 Reason: Interactive button title must be 20 characters or fewer."

        error_msg = f"Meta API Error ({err_code or 'Failed'}): {raw_err}"
        if details:
            error_msg += f" - {details}"
        error_msg += user_hint

    # Log to WhatsAppMessage DB table if organization is available
    status_str = 'Sent' if meta_api_sent else ('Failed' if error_msg else 'Dispatched')
    wa_msg_id = None
    
    if org:
        wa_msg = WhatsAppMessage.objects.create(
            organization=org,
            lead=lead,
            user=user,
            recipient_phone=cleaned_phone,
            template_name=template_name or '',
            message_content=message_text or f"[Template: {template_name}]",
            meta_message_id=meta_message_id or '',
            status=status_str,
            error_message=error_msg or '',
            buttons_json=json.dumps(buttons)
        )
        wa_msg_id = wa_msg.id

    if error_msg:
        return {
            'success': False,
            'error': error_msg,
            'payload': payload,
            'api_response': api_response,
            'whatsapp_message_id': wa_msg_id
        }

    # Log to Lead Activity Timeline if lead is linked
    if lead and org:
        button_titles = ", ".join(f"[{b.get('text') or b.get('title')}]" for b in buttons[:3])
        log_desc = f"Sent WhatsApp Message to +{cleaned_phone} (ID: {meta_message_id or 'Sent'}):\n\"{message_text[:120]}\""
        if button_titles:
            log_desc += f"\nButtons: {button_titles}"

        Activity.objects.create(
            organization=org,
            lead=lead,
            user=user,
            type="WhatsApp Message",
            description=log_desc
        )

    return {
        'success': True,
        'meta_api_sent': meta_api_sent,
        'meta_message_id': meta_message_id,
        'message': f"WhatsApp message successfully delivered to +{cleaned_phone}!",
        'payload': payload,
        'api_response': api_response,
        'whatsapp_message_id': wa_msg_id
    }
