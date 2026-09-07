import logging
import datetime
import re
import time
import paramiko
import telnetlib
from sqlalchemy import select, delete
from app.database import AsyncSessionLocal, SystemSettings, OLTONU, OLTCardStats, OLTPonPort, OLTMetricsHistory

logger = logging.getLogger("olt_collector")

def parse_card_stats(output_text: str):
    stats = {}
    for line in output_text.splitlines():
        match = re.search(r'^\s*(\d+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+(\d+)\s+(\d+)\s+([^\s]+.*?)\s+(\d+:\d+:\d+:\d+)\s+([\d\.]+)', line)
        if match:
            slot, idle, usage, mem_used_pct, total_mem, avail_mem, status, uptime, fw = match.groups()
            stats = {
                "cpu_usage": float(usage),
                "memory_used_percent": float(mem_used_pct),
                "memory_avail_kb": float(avail_mem),
                "uptime": uptime,
                "firmware_version": fw
            }
            break
    return stats


def parse_olt_show_port(output_text: str):
    ports = []
    for line in output_text.splitlines():
        match = re.search(r'^\s*(\d+)\s+(\d+\s*C)\s+([\d\.]+\s*V)\s+(\d+\s*mA)\s+([-\d\.]+\s*dBm)\s+([-\w\.]+\s*dBm)\s+(\w+)', line)
        if match:
            port_id, temp, volt, bias, tx_pow, rx_pow, status = match.groups()
            tx_val = float(re.sub(r'[^\d\.-]', '', tx_pow)) if 'dBm' in tx_pow else 0.0
            rx_val = float(re.sub(r'[^\d\.-]', '', rx_pow)) if ('dBm' in rx_pow and 'inf' not in rx_pow) else -99.0
            port_status = "OFFLINE" if rx_val <= -90.0 else "ONLINE"
            ports.append({
                "port_number": int(port_id),
                "temperature": temp,
                "voltage": volt,
                "tx_power_dbm": tx_val,
                "rx_power_dbm": rx_val,
                "status": port_status
            })
    return ports


def parse_onu_descriptions(output_text: str):
    descriptions = {}
    idx_desc = output_text.find("onu description show")
    if idx_desc != -1:
        desc_block = output_text[idx_desc:]
        for next_cmd in ["onu inventory", "onu status", "olt show port"]:
            idx_next = desc_block.find(next_cmd, 20)
            if idx_next != -1:
                desc_block = desc_block[:idx_next]
                break
    else:
        desc_block = output_text

    for line in desc_block.splitlines():
        line_str = line.strip()
        if "Description" in line_str or "=====" in line_str or "onu description show" in line_str:
            continue
        match = re.search(r'gpon\s+(\d+)\s+onu\s+(\d+)\s+(.+)$', line_str, re.IGNORECASE)
        if match:
            gpon_num, onu_num, desc = match.groups()
            desc_clean = desc.strip()
            if desc_clean:
                key = f"{gpon_num}:{onu_num}"
                descriptions[key] = desc_clean
    return descriptions


def parse_onu_inventory(output_text: str):
    inventory = {}
    for line in output_text.splitlines():
        line_str = line.strip()
        if not line_str.lower().startswith('gpon'):
            continue
        parts = re.split(r'\s{2,}', line_str)
        if len(parts) >= 4:
            gpon_match = re.search(r'gpon\s+(\d+)\s+onu\s+(\d+)', parts[0], re.IGNORECASE)
            if not gpon_match:
                continue
            gpon_num, onu_num = gpon_match.groups()
            serial = parts[1]
            vendor = parts[2]
            
            model = ''
            ont_ver = ''
            sw_ver = ''

            if len(parts) >= 6:
                model = parts[3]
                ont_ver = parts[4]
                sw_ver = parts[5]
            elif len(parts) == 5:
                sw_ver = parts[4]
                sub_parts = parts[3].rsplit(' ', 1)
                model = sub_parts[0]
                ont_ver = sub_parts[1] if len(sub_parts) > 1 else ''
            elif len(parts) == 4:
                model = parts[3]

            key = f'{gpon_num}:{onu_num}'
            inventory[key] = {
                'serial': serial.strip(),
                'vendor': vendor.strip(),
                'model': model.strip(),
                'ont_version': ont_ver.strip(),
                'software_version': sw_ver.strip()
            }
    return inventory


def parse_onu_status(output_text: str):
    onus = []
    current_gpon = 1
    
    for line in output_text.splitlines():
        line_str = line.strip()
        gpon_match = re.search(r'^\s*GPON\s+(\d+)', line_str, re.IGNORECASE)
        if gpon_match:
            current_gpon = int(gpon_match.group(1))
            continue
        
        parts = line_str.split()
        if len(parts) >= 3 and parts[0].isdigit() and len(parts[1]) >= 6:
            try:
                onu_id = int(parts[0])
            except ValueError:
                continue
                
            serial = parts[1]
            oper_status = parts[2]
            
            if oper_status.lower() in ["active", "ok"]:
                omci_status = parts[3] if len(parts) > 3 else "OK"
                
                dbm_matches = re.findall(r'([-\d\.]+)\s*dBm', line_str)
                olt_rx = float(dbm_matches[0]) if len(dbm_matches) >= 1 else 0.0
                onu_rx = float(dbm_matches[1]) if len(dbm_matches) >= 2 else 0.0
                
                dist_match = re.search(r'dBm\s+([0-9\.]+)', line_str)
                distance = float(dist_match.group(1)) if dist_match else 0.0
                
                uptime_match = re.search(r'(\d+:\d+:\d+:\d+|\d+:\d+:\d+)', line_str)
                uptime = uptime_match.group(1) if uptime_match else "-"
                
                status = "online"
            else:
                omci_status = "-"
                olt_rx = 0.0
                onu_rx = 0.0
                distance = 0.0
                uptime = "-"
                status = "offline"

            onus.append({
                "gpon_port": current_gpon,
                "slot_port": f"GPON {current_gpon}",
                "onu_id": onu_id,
                "serial": serial,
                "oper_status": oper_status,
                "status": status,
                "omci_status": omci_status,
                "olt_rx_power": olt_rx,
                "onu_rx_power": onu_rx,
                "rx_power": olt_rx if olt_rx != 0.0 else onu_rx,
                "tx_power": 2.15,
                "distance_km": distance,
                "uptime": uptime
            })

    return onus


def telnet_exec_cmd(tn, cmd: str, cmd_delay=0.5, timeout=25):
    tn.write(cmd.encode('utf-8') + b'\r\n')
    time.sleep(cmd_delay)
    
    full_bytes = b""
    start_t = time.time()
    while time.time() - start_t < timeout:
        chunk = tn.read_very_eager()
        if chunk:
            full_bytes += chunk
            if b'--More--' in chunk or b'--Mais--' in chunk:
                tn.write(b' ')
                time.sleep(0.2)
        else:
            time.sleep(0.4)
            decoded = full_bytes.decode('utf-8', errors='ignore').strip()
            if decoded.endswith('>') or decoded.endswith('#') or 'intelbras-olt' in decoded[-30:]:
                break
    return full_bytes.decode('utf-8', errors='ignore')


def collect_via_telnet(ip, port, user, password, cmd_delay=0.5):
    logger.info(f"Connecting via Telnet to Intelbras OLT {ip}:{port}...")
    tn = telnetlib.Telnet(ip, port, timeout=10)
    
    # Login prompt
    tn.expect([b'login:', b'User:', b'username:'], timeout=10)
    tn.write(user.encode('utf-8') + b'\r\n')
    
    # Password prompt
    tn.expect([b'Password:', b'password:'], timeout=10)
    tn.write(password.encode('utf-8') + b'\r\n')
    
    time.sleep(1.0)
    tn.read_very_eager()

    c1 = telnet_exec_cmd(tn, "card stats", cmd_delay)
    c2 = telnet_exec_cmd(tn, "olt show port", cmd_delay)
    c3 = telnet_exec_cmd(tn, "onu description show", cmd_delay)
    c4 = telnet_exec_cmd(tn, "onu inventory", cmd_delay)
    c5 = telnet_exec_cmd(tn, "onu status", cmd_delay, timeout=35)
    
    tn.close()
    return c1 + "\n" + c2 + "\n" + c3 + "\n" + c4 + "\n" + c5


def collect_via_ssh(ip, port, user, password, cmd_delay=0.5):
    logger.info(f"Connecting via SSH to Intelbras OLT {ip}:{port}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ip, port=port, username=user, password=password, timeout=8, look_for_keys=False)
    
    channel = client.invoke_shell()
    time.sleep(0.5)

    commands = [
        "card stats",
        "olt show port",
        "onu description show",
        "onu inventory",
        "onu status"
    ]

    full_output = ""
    for cmd in commands:
        channel.send(cmd + "\n")
        time.sleep(cmd_delay)
        while channel.recv_ready():
            full_output += channel.recv(4096).decode('utf-8', errors='ignore')
    
    client.close()
    return full_output


async def run_olt_routine():
    logger.info("Starting Intelbras OLT 8820 routine collection...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SystemSettings).where(SystemSettings.id == 1))
        settings = result.scalar_one_or_none()
        if not settings:
            logger.warning("System settings not found.")
            return

        ip = settings.olt_ip
        port = settings.olt_port or 2323
        user = settings.olt_user
        password = settings.olt_password
        cmd_delay = settings.olt_command_delay or 0.5

        full_output = ""
        is_success = False

        # If port is Telnet (23, 2323, etc.), try Telnet first
        if port in [23, 2323]:
            try:
                full_output = collect_via_telnet(ip, port, user, password, cmd_delay)
                is_success = True
            except Exception as e:
                logger.warning(f"Telnet connection failed ({e}). Trying SSH fallback...")

        # Fallback to SSH or SSH default
        if not is_success:
            try:
                full_output = collect_via_ssh(ip, port, user, password, cmd_delay)
                is_success = True
            except Exception as e:
                logger.warning(f"SSH connection failed ({e}). Trying Telnet fallback...")
                if port not in [23, 2323]:
                    try:
                        full_output = collect_via_telnet(ip, port, user, password, cmd_delay)
                        is_success = True
                    except Exception as te:
                        logger.error(f"Telnet fallback also failed ({te}).")

        if not is_success or not full_output:
            logger.warning("OLT not reachable or no data returned. Skipping database update.")
            return

        card_stats_data = parse_card_stats(full_output)
        pon_ports_data = parse_olt_show_port(full_output)
        descriptions_map = parse_onu_descriptions(full_output)
        inventory_map = parse_onu_inventory(full_output)
        onus_collected = parse_onu_status(full_output)

        logger.info(f"OLT Data Parsed -> Card Stats: {bool(card_stats_data)}, Ports: {len(pon_ports_data)}, ONUs: {len(onus_collected)}")

        # Save OLT Card Stats
        if card_stats_data:
            await session.execute(delete(OLTCardStats))
            session.add(OLTCardStats(
                cpu_usage=card_stats_data.get("cpu_usage", 0.0),
                memory_used_percent=card_stats_data.get("memory_used_percent", 0.0),
                memory_avail_kb=card_stats_data.get("memory_avail_kb", 0.0),
                uptime=card_stats_data.get("uptime", ""),
                firmware_version=card_stats_data.get("firmware_version", ""),
                timestamp=datetime.datetime.now()
            ))

        # Save PON Transceiver Ports
        if pon_ports_data:
            await session.execute(delete(OLTPonPort))
            for p in pon_ports_data:
                session.add(OLTPonPort(
                    port_number=p["port_number"],
                    temperature=p["temperature"],
                    voltage=p["voltage"],
                    tx_power_dbm=p["tx_power_dbm"],
                    rx_power_dbm=p["rx_power_dbm"],
                    status=p["status"],
                    updated_at=datetime.datetime.now()
                ))

        # Update Database ONUs
        await session.execute(delete(OLTONU))
        
        online_count = 0
        offline_count = 0
        total_rx = 0.0

        for o in onus_collected:
            key = f"{o['gpon_port']}:{o['onu_id']}"
            name = descriptions_map.get(key, f"ONU_{o['serial']}")
            inv = inventory_map.get(key, {})
            vendor = inv.get("vendor", "")
            model = inv.get("model", "")
            ont_ver = inv.get("ont_version", "")
            sw_ver = inv.get("software_version", "")

            if o["status"] == "online":
                online_count += 1
                total_rx += o["rx_power"]
            else:
                offline_count += 1

            session.add(OLTONU(
                slot_port=o["slot_port"],
                onu_id=o["onu_id"],
                name=name,
                serial=o["serial"],
                status=o["status"],
                omci_status=o["omci_status"],
                olt_rx_power=o["olt_rx_power"],
                onu_rx_power=o["onu_rx_power"],
                rx_power=o["rx_power"],
                tx_power=o["tx_power"],
                distance_km=o["distance_km"],
                uptime=o["uptime"],
                vendor_id=vendor,
                model_id=model,
                ont_version=ont_ver,
                software_version=sw_ver,
                updated_at=datetime.datetime.now()
            ))

        avg_rx = round(total_rx / online_count, 2) if online_count > 0 else 0.0

        history_entry = OLTMetricsHistory(
            total_onus=len(onus_collected),
            online_onus=online_count,
            offline_onus=offline_count,
            avg_rx_power=avg_rx,
            timestamp=datetime.datetime.now()
        )
        session.add(history_entry)

        await session.commit()
        logger.info(f"Intelbras OLT routine completed. Total ONUs: {len(onus_collected)} (Online: {online_count}, Offline: {offline_count}, Avg RX: {avg_rx} dBm)")
