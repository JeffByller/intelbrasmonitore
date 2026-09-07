import logging
import requests

logger = logging.getLogger("telegram_service")

def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> bool:
    """
    Sends HTML/Markdown formatted notification message to Telegram group/chat.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID not configured. Skipping alert.")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram notification sent successfully.")
            return True
        else:
            logger.error(f"Failed to send Telegram message: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending Telegram notification: {e}")
        return False


def notify_bgp_down(bot_token: str, chat_id: str, peer_name: str, remote_ip: str, old_state: str, new_state: str):
    message = (
        f"⚠️ <b>ALERTA BGP - QUEDA DE SESSÃO</b>\n\n"
        f"<b>MikroTik Concentrador</b>\n"
        f"🔴 <b>Peer:</b> {peer_name} ({remote_ip})\n"
        f"❌ <b>Estado Anterior:</b> {old_state}\n"
        f"⚠️ <b>Estado Atual:</b> <code>{new_state}</code>\n\n"
        f"<i>Verifique a operadora/link de transporte urgentemente!</i>"
    )
    return send_telegram_alert(bot_token, chat_id, message)


def notify_bgp_up(bot_token: str, chat_id: str, peer_name: str, remote_ip: str, uptime: str):
    message = (
        f"✅ <b>NOTIFICAÇÃO BGP - SESSÃO RESTABELECIDA</b>\n\n"
        f"<b>MikroTik Concentrador</b>\n"
        f"🟢 <b>Peer:</b> {peer_name} ({remote_ip})\n"
        f"STATUS: <code>ESTABLISHED</code>\n"
        f"⏱️ <b>Uptime Sessão:</b> {uptime}\n\n"
        f"<i>A sessão BGP voltou a operar normalmente!</i>"
    )
    return send_telegram_alert(bot_token, chat_id, message)


def notify_client_drop(bot_token: str, chat_id: str, previous_count: int, current_count: int, drop_diff: int):
    message = (
        f"⚠️ <b>ALERTA DE MONITORAMENTO - MIKROTIK</b>\n\n"
        f"⚡ <b>Queda de Conexões Detectada!</b>\n"
        f"📊 <b>Conexões na rotina anterior:</b> {previous_count}\n"
        f"📉 <b>Conexões na rotina atual:</b> {current_count}\n"
        f"🚨 <b>Clientes desconectados:</b> <code>{drop_diff} clientes</code>\n\n"
        f"<i>Possível desconexão em massa ou oscilação de concentrador.</i>"
    )
    return send_telegram_alert(bot_token, chat_id, message)
