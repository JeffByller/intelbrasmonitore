import logging
import datetime
import socket
import ssl
import binascii
import requests
from requests.auth import HTTPBasicAuth
from sqlalchemy import select, delete
from app.database import (
    AsyncSessionLocal, SystemSettings, MikrotikMetrics, BgpPeerState, 
    MikrotikTopClient, MikrotikInterface, MikrotikRadius, MikrotikBlockedClient
)
from app.services.telegram import notify_bgp_down, notify_bgp_up, notify_client_drop

logger = logging.getLogger("mikrotik_collector")

# Native RouterOS API Protocol implementation for Port 8728/8729
class RouterOSApiProtocol:
    def __init__(self, host, port=8728, timeout=8):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.sk = None

    def connect(self, username, password):
        self.sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sk.settimeout(self.timeout)
        self.sk.connect((self.host, self.port))
        
        # Try RouterOS v7 plain login first
        reply = self.talk(["/login", f"=name={username}", f"=password={password}"])
        if reply and "!done" in reply[0] and not any("=ret=" in sentence for sentence in reply):
            return True
        
        # Fallback to RouterOS v6 challenge-response login
        challenge_reply = self.talk(["/login"])
        chall = None
        for sentence in challenge_reply:
            for word in sentence:
                if word.startswith("=ret="):
                    chall = word[5:]
                    break
        
        if chall:
            import hashlib
            chal_bytes = binascii.unhexlify(chall)
            md = hashlib.md5(b'\x00' + password.encode('utf-8') + chal_bytes).hexdigest()
            reply = self.talk(["/login", f"=name={username}", f"=response=00{md}"])
            if reply and "!done" in reply[0]:
                return True
        
        return False

    def write_length(self, length):
        if length < 0x80:
            self.sk.send(bytes([length]))
        elif length < 0x4000:
            self.sk.send(bytes([(length >> 8) | 0x80, length & 0xFF]))
        elif length < 0x200000:
            self.sk.send(bytes([(length >> 16) | 0xC0, (length >> 8) & 0xFF, length & 0xFF]))
        elif length < 0x10000000:
            self.sk.send(bytes([(length >> 24) | 0xE0, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF]))
        else:
            self.sk.send(bytes([0xF0, (length >> 24) & 0xFF, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF]))

    def write_word(self, word):
        b = word.encode('utf-8')
        self.write_length(len(b))
        self.sk.send(b)

    def write_sentence(self, sentence):
        for word in sentence:
            self.write_word(word)
        self.write_word("")

    def read_length(self):
        b = self.sk.recv(1)
        if not b:
            return 0
        c = b[0]
        if (c & 0x80) == 0:
            return c
        elif (c & 0xC0) == 0x80:
            b2 = self.sk.recv(1)
            return ((c & 0x3F) << 8) + b2[0]
        elif (c & 0xE0) == 0xC0:
            b2 = self.sk.recv(2)
            return ((c & 0x1F) << 16) + (b2[0] << 8) + b2[1]
        elif (c & 0xF0) == 0xE0:
            b2 = self.sk.recv(3)
            return ((c & 0x0F) << 24) + (b2[0] << 16) + (b2[1] << 8) + b2[2]
        else:
            b2 = self.sk.recv(4)
            return (b2[0] << 24) + (b2[1] << 16) + (b2[2] << 8) + b2[3]

    def read_word(self):
        length = self.read_length()
        if length == 0:
            return ""
        buf = bytearray()
        while len(buf) < length:
            chunk = self.sk.recv(length - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return buf.decode('utf-8', errors='ignore')

    def read_sentence(self):
        sentence = []
        while True:
            word = self.read_word()
            if word == "":
                break
            sentence.append(word)
        return sentence

    def talk(self, sentence):
        self.write_sentence(sentence)
        reply = []
        while True:
            s = self.read_sentence()
            if not s:
                break
            reply.append(s)
            if s[0] == "!done":
                break
        return reply

    def query(self, command):
        raw_reply = self.talk([command])
        results = []
        for sentence in raw_reply:
            if sentence and sentence[0] == "!re":
                item = {}
                for word in sentence[1:]:
                    if word.startswith("="):
                        parts = word[1:].split("=", 1)
                        if len(parts) == 2:
                            item[parts[0]] = parts[1]
                results.append(item)
        return results

    def close(self):
        if self.sk:
            try:
                self.sk.close()
            except Exception:
                pass


def format_readable_uptime(uptime_str: str) -> str:
    if not uptime_str or uptime_str.strip() in ["-", "", "0s"]:
        return "-"
    
    uptime_str = uptime_str.strip()
    
    # Handle dd:hh:mm:ss format
    if ":" in uptime_str and not any(c in uptime_str for c in ["w", "d", "h", "m", "s"]):
        parts = uptime_str.split(":")
        try:
            if len(parts) == 4:
                d, h, m, s = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                res = []
                if d > 0: res.append(f"{d} {'dia' if d == 1 else 'dias'}")
                if h > 0: res.append(f"{h}h")
                if m > 0: res.append(f"{m}m")
                return ", ".join(res) if res else f"{s}s"
            elif len(parts) == 3:
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                res = []
                if h > 0: res.append(f"{h}h")
                if m > 0: res.append(f"{m}m")
                return ", ".join(res) if res else f"{s}s"
        except Exception:
            pass

    # Handle MikroTik 2w5d16h40m17s style
    import re
    weeks = re.search(r'(\d+)w', uptime_str)
    days = re.search(r'(\d+)d', uptime_str)
    hours = re.search(r'(\d+)h', uptime_str)
    minutes = re.search(r'(\d+)m', uptime_str)
    seconds = re.search(r'(\d+)s', uptime_str)
    
    w = int(weeks.group(1)) if weeks else 0
    d = int(days.group(1)) if days else 0
    h = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    s = int(seconds.group(1)) if seconds else 0
    
    total_days = (w * 7) + d
    parts = []
    if total_days > 0:
        parts.append(f"{total_days} {'dia' if total_days == 1 else 'dias'}")
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    if s > 0 and total_days == 0 and h == 0:
        parts.append(f"{s}s")
        
    return ", ".join(parts[:3]) if parts else uptime_str


parse_uptime_seconds = lambda u: 0 # Fallback helper


def parse_bgp_peer_item(b: dict) -> dict:
    peer_name = b.get("name", b.get("remote.address", b.get("remote-address", "BGP_Peer")))
    remote_addr = b.get("remote.address", b.get("remote-address", "0.0.0.0"))
    remote_as = str(b.get("remote.as", b.get("remote-as", "")))
    raw_uptime = str(b.get("uptime", "0s"))
    uptime_b = format_readable_uptime(raw_uptime)
    
    is_disabled = str(b.get("disabled", "false")).lower() in ["true", "yes", "1"]
    raw_state = str(b.get("state", "")).lower()
    raw_established = str(b.get("established", "")).lower()

    if is_disabled:
        state = "disabled"
        is_est = False
    elif raw_state == "established" or raw_established in ["true", "yes", "1"]:
        state = "established"
        is_est = True
    elif raw_state != "":
        state = raw_state
        is_est = False
    else:
        if raw_uptime in ["0s", "", "00:00:00"]:
            state = "idle"
            is_est = False
        else:
            state = "established"
            is_est = True

    return {
        "name": peer_name,
        "remote_address": remote_addr,
        "remote_as": remote_as,
        "state": state,
        "is_established": is_est,
        "uptime": uptime_b
    }


async def run_mikrotik_routine():
    logger.info("Starting MikroTik routine collection...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SystemSettings).where(SystemSettings.id == 1))
        settings = result.scalar_one_or_none()
        if not settings:
            logger.warning("System settings not found.")
            return

        ip = settings.mikrotik_ip
        port = settings.mikrotik_port or 8728
        user = settings.mikrotik_user
        password = settings.mikrotik_password
        drop_threshold = settings.mikrotik_drop_threshold or 2
        bot_token = settings.telegram_bot_token
        chat_id = settings.telegram_chat_id
        alerts_enabled = settings.telegram_alerts_enabled

        bgp_peers = []
        clients = []
        interfaces = []
        radius_list = []
        blocked_clients = []

        is_connected = False

        cpu_load = 0
        free_mem = 0.0
        total_mem = 0.0
        uptime = "0s"
        board_name = "MikroTik"
        active_count = 0

        # Method 1: RouterOS Native API (Port 8728 / 8729)
        if port in [8728, 8729]:
            try:
                api = RouterOSApiProtocol(ip, port=port, timeout=8)
                if api.connect(user, password):
                    is_connected = True
                    logger.info(f"Connected to MikroTik via Native API (port {port}).")
                    
                    # 1. System Resource
                    res = api.query("/system/resource/print")
                    if res:
                        r = res[0]
                        total_mem = float(r.get("total-memory", 0)) / (1024 * 1024)
                        free_mem = float(r.get("free-memory", 0)) / (1024 * 1024)
                        cpu_load = int(r.get("cpu-load", 0))
                        uptime = format_readable_uptime(str(r.get("uptime", "0s")))
                        board_name = str(r.get("board-name", "MikroTik"))

                    # 2. Active PPPoE Connections
                    ppp = api.query("/ppp/active/print")
                    active_count = len(ppp)
                    for c in ppp:
                        clients.append({
                            "username": c.get("name", "desconhecido"),
                            "ip_address": c.get("address", "0.0.0.0"),
                            "mac_address": c.get("caller-id", "00:00:00:00:00:00"),
                            "uptime": format_readable_uptime(c.get("uptime", "0s")),
                            "raw_uptime": c.get("uptime", "0s"),
                            "service": c.get("service", "pppoe")
                        })

                    # 3. BGP Peers (RouterOS v6 & v7)
                    bgp = api.query("/routing/bgp/peer/print")
                    if not bgp:
                        bgp = api.query("/routing/bgp/session/print")

                    for b in bgp:
                        bgp_peers.append(parse_bgp_peer_item(b))

                    # 4. Ethernet Interfaces
                    if_data = api.query("/interface/ethernet/print")
                    if not if_data:
                        if_data = api.query("/interface/print")

                    for item in if_data:
                        if_type = item.get("type", "ether")
                        if if_type in ["ether", "ethernet"] or "ether" in item.get("name", "").lower():
                            is_running = str(item.get("running", "true")).lower() in ["true", "yes", "1"]
                            is_disabled = str(item.get("disabled", "false")).lower() in ["true", "yes", "1"]
                            interfaces.append({
                                "name": item.get("name", "ether"),
                                "type": "ethernet",
                                "running": is_running,
                                "disabled": is_disabled,
                                "comment": item.get("comment", ""),
                                "mac_address": item.get("mac-address", item.get("mac", ""))
                            })

                    # 5. Radius Server Status
                    rad_data = api.query("/radius/print")
                    for rad in rad_data:
                        rad_addr = rad.get("address", "0.0.0.0")
                        rad_service = rad.get("service", "ppp")
                        rad_timeout = rad.get("timeout", "300ms")
                        rad_disabled = str(rad.get("disabled", "false")).lower() in ["true", "yes", "1"]
                        rad_status = "Desativado" if rad_disabled else "UP (Autenticando OK)"
                        radius_list.append({
                            "address": rad_addr,
                            "service": rad_service,
                            "timeout": rad_timeout,
                            "disabled": rad_disabled,
                            "status": rad_status,
                            "requests": int(rad.get("requests", 0)),
                            "accepts": int(rad.get("accepts", 0)),
                            "rejects": int(rad.get("rejects", 0))
                        })

                    # 6. Blocked Clients (Address List rbfull_pgcorte)
                    addr_data = api.query("/ip/firewall/address-list/print")
                    blocked_ips = {}
                    for addr in addr_data:
                        if addr.get("list") == "rbfull_pgcorte":
                            ip_addr = addr.get("address", "")
                            if ip_addr:
                                blocked_ips[ip_addr] = addr.get("list")

                    # Cross-reference blocked IPs with active PPPoE sessions
                    active_by_ip = {c["ip_address"]: c for c in clients}
                    for ip_addr, list_name in blocked_ips.items():
                        if ip_addr in active_by_ip:
                            c = active_by_ip[ip_addr]
                            blocked_clients.append({
                                "username": c["username"],
                                "ip_address": ip_addr,
                                "mac_address": c["mac_address"],
                                "uptime": c["uptime"],
                                "list_name": list_name
                            })
                        else:
                            blocked_clients.append({
                                "username": "Cliente Offline (Desconectado)",
                                "ip_address": ip_addr,
                                "mac_address": "-",
                                "uptime": "-",
                                "list_name": list_name
                            })

                    api.close()
            except Exception as e:
                logger.warning(f"Native RouterOS API error ({e}). Trying REST API fallback...")

        # Method 2: REST API Fallback
        if not is_connected:
            rest_port = port if port in [80, 443, 8080] else 80
            base_url = f"http://{ip}:{rest_port}/rest" if rest_port != 80 else f"http://{ip}/rest"
            try:
                auth = HTTPBasicAuth(user, password)
                res_resp = requests.get(f"{base_url}/system/resource", auth=auth, timeout=5)
                if res_resp.status_code == 200:
                    res_data = res_resp.json()
                    if isinstance(res_data, list) and len(res_data) > 0:
                        res_data = res_data[0]
                    total_mem = float(res_data.get("total-memory", 0)) / (1024 * 1024)
                    free_mem = float(res_data.get("free-memory", 0)) / (1024 * 1024)
                    cpu_load = int(res_data.get("cpu-load", 0))
                    uptime = format_readable_uptime(str(res_data.get("uptime", "0s")))
                    board_name = str(res_data.get("board-name", "MikroTik Router"))
                    is_connected = True

                ppp_resp = requests.get(f"{base_url}/ppp/active", auth=auth, timeout=5)
                if ppp_resp.status_code == 200:
                    ppp_data = ppp_resp.json()
                    active_count = len(ppp_data)
                    for c in ppp_data:
                        clients.append({
                            "username": c.get("name", "desconhecido"),
                            "ip_address": c.get("address", "0.0.0.0"),
                            "mac_address": c.get("caller-id", "00:00:00:00:00:00"),
                            "uptime": format_readable_uptime(c.get("uptime", "0s")),
                            "service": c.get("service", "pppoe")
                        })

                bgp_resp = requests.get(f"{base_url}/routing/bgp/peer", auth=auth, timeout=5)
                if bgp_resp.status_code != 200:
                    bgp_resp = requests.get(f"{base_url}/routing/bgp/session", auth=auth, timeout=5)
                
                if bgp_resp.status_code == 200:
                    bgp_data = bgp_resp.json()
                    for b in bgp_data:
                        bgp_peers.append(parse_bgp_peer_item(b))
            except Exception as e:
                logger.warning(f"REST API connection failed ({e}). IP {ip}:{port} unreached.")

        if not is_connected:
            logger.warning(f"MikroTik unreached. IP {ip}:{port} - Verify credentials or active API service.")
            return

        # Save Metrics History
        metric_entry = MikrotikMetrics(
            active_connections=active_count,
            cpu_load=cpu_load,
            free_memory_mb=free_mem,
            total_memory_mb=total_mem,
            uptime=uptime,
            board_name=board_name,
            timestamp=datetime.datetime.now()
        )
        session.add(metric_entry)

        # Check Disconnection Drop Alert
        last_metrics = await session.execute(
            select(MikrotikMetrics).order_by(MikrotikMetrics.id.desc()).offset(1).limit(1)
        )
        prev_metric = last_metrics.scalar_one_or_none()
        if prev_metric:
            prev_count = prev_metric.active_connections
            drop_diff = prev_count - active_count
            if drop_diff >= drop_threshold and alerts_enabled:
                logger.info(f"Client drop detected! Previous: {prev_count}, Current: {active_count}, Drop: {drop_diff}")
                notify_client_drop(bot_token, chat_id, prev_count, active_count, drop_diff)

        # Update BGP States & Check Alert
        existing_bgp = await session.execute(select(BgpPeerState))
        existing_bgp_map = {b.peer_name: b for b in existing_bgp.scalars().all()}

        for b_info in bgp_peers:
            peer_name = b_info["name"]
            current_state = b_info["state"]
            is_est = b_info["is_established"]
            
            if peer_name in existing_bgp_map:
                peer_db = existing_bgp_map[peer_name]
                old_state = peer_db.state
                was_est = peer_db.is_established
                
                if was_est and not is_est and alerts_enabled:
                    logger.warning(f"BGP SESSION DROPPED! Peer: {peer_name}")
                    notify_bgp_down(bot_token, chat_id, peer_name, b_info["remote_address"], old_state, current_state)
                elif not was_est and is_est and alerts_enabled:
                    logger.info(f"BGP SESSION RECOVERED! Peer: {peer_name}")
                    notify_bgp_up(bot_token, chat_id, peer_name, b_info["remote_address"], b_info["uptime"])
                
                peer_db.state = current_state
                peer_db.is_established = is_est
                peer_db.uptime = b_info["uptime"]
                peer_db.remote_address = b_info["remote_address"]
                peer_db.remote_as = b_info["remote_as"]
                peer_db.last_check = datetime.datetime.now()
            else:
                new_peer = BgpPeerState(
                    peer_name=peer_name,
                    remote_address=b_info["remote_address"],
                    remote_as=b_info["remote_as"],
                    state=current_state,
                    is_established=is_est,
                    uptime=b_info["uptime"],
                    last_check=datetime.datetime.now()
                )
                session.add(new_peer)

        # Refresh Ethernet Interfaces
        await session.execute(delete(MikrotikInterface))
        for eth in interfaces:
            session.add(MikrotikInterface(
                name=eth["name"],
                type=eth["type"],
                running=eth["running"],
                disabled=eth["disabled"],
                comment=eth["comment"],
                mac_address=eth["mac_address"],
                last_check=datetime.datetime.now()
            ))

        # Refresh Radius Status
        await session.execute(delete(MikrotikRadius))
        for rad in radius_list:
            session.add(MikrotikRadius(
                address=rad["address"],
                service=rad["service"],
                timeout=rad["timeout"],
                disabled=rad["disabled"],
                status=rad["status"],
                requests=rad["requests"],
                accepts=rad["accepts"],
                rejects=rad["rejects"],
                last_check=datetime.datetime.now()
            ))

        # Refresh Blocked Clients
        await session.execute(delete(MikrotikBlockedClient))
        for bc in blocked_clients:
            session.add(MikrotikBlockedClient(
                username=bc["username"],
                ip_address=bc["ip_address"],
                mac_address=bc["mac_address"],
                uptime=bc["uptime"],
                list_name=bc["list_name"],
                updated_at=datetime.datetime.now()
            ))

        # Refresh Top Clients
        await session.execute(delete(MikrotikTopClient))
        for idx, c in enumerate(clients):
            session.add(MikrotikTopClient(
                username=c["username"],
                ip_address=c["ip_address"],
                mac_address=c["mac_address"],
                uptime=c["uptime"],
                uptime_seconds=idx,
                service=c["service"]
            ))

        await session.commit()
        logger.info(f"MikroTik collection completed successfully. Active: {active_count}, Interfaces: {len(interfaces)}, Radius: {len(radius_list)}, Blocked: {len(blocked_clients)}")
