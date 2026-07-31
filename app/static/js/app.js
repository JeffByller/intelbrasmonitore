let allOnus = [];
let currentPage = 1;
const PAGE_SIZE = 15;
let oltChart = null;
let mikrotikChart = null;

document.addEventListener("DOMContentLoaded", () => {
    initDashboard();
    setInterval(loadSummaryData, 10000); // Poll summary stats every 10 seconds
});

function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(content => content.classList.remove("active"));
    
    event.currentTarget.classList.add("active");
    document.getElementById(tabId).classList.add("active");

    if (tabId === 'tab-olt') loadONUs();
    if (tabId === 'tab-mikrotik') loadMikrotikDetails();
    if (tabId === 'tab-general') {
        loadHistoryCharts();
        loadOLTPorts();
    }
}

async function initDashboard() {
    await loadSummaryData();
    await loadHistoryCharts();
    await loadOLTPorts();
    await loadMikrotikDetails();
    await loadONUs();
}

async function loadSummaryData() {
    try {
        const res = await fetch("/api/dashboard/summary");
        if (!res.ok) {
            if (res.status === 401) window.location.href = "/login";
            return;
        }
        const data = await res.json();

        // Update OLT Stat Card
        document.getElementById("stat-olt-online").innerText = data.olt.online_onus;
        document.getElementById("stat-olt-total").innerText = data.olt.total_onus;
        document.getElementById("stat-olt-offline").innerText = data.olt.offline_onus;
        document.getElementById("stat-olt-cpu").innerText = `${data.olt.cpu_usage}%`;
        document.getElementById("stat-olt-mem").innerText = `${data.olt.memory_used_percent}%`;
        document.getElementById("stat-olt-fw").innerText = data.olt.firmware_version;
        document.getElementById("stat-olt-avg-rx").innerText = `${data.olt.avg_rx_power} dBm`;
        document.getElementById("stat-olt-time").innerText = data.olt.last_update;

        // Update MikroTik Stat Card
        document.getElementById("stat-mk-connections").innerText = data.mikrotik.active_connections;
        document.getElementById("stat-mk-cpu").innerText = `${data.mikrotik.cpu_load}%`;
        document.getElementById("stat-mk-ram").innerText = `${Math.round(data.mikrotik.free_memory_mb)} MB`;
        document.getElementById("stat-mk-blocked").innerText = data.mikrotik.blocked_count || 0;
        document.getElementById("stat-mk-uptime").innerText = data.mikrotik.uptime;
        document.getElementById("stat-mk-board").innerText = data.mikrotik.board_name;
        document.getElementById("stat-mk-time").innerText = data.mikrotik.last_update;

        // Update BGP Stat Card
        const established = data.bgp.established_sessions;
        const total = data.bgp.total_sessions;
        document.getElementById("stat-bgp-established").innerText = `${established} / ${total || 4}`;

        const bgpPulse = document.getElementById("bgp-pulse");
        if (established === total && total > 0) {
            bgpPulse.className = "pulse-indicator green";
        } else {
            bgpPulse.className = "pulse-indicator red";
        }
    } catch (err) {
        console.error("Error loading summary:", err);
    }
}

async function loadOLTPorts() {
    try {
        const res = await fetch("/api/dashboard/olt/ports");
        const ports = await res.json();
        const container = document.getElementById("pon-ports-cards");
        if (!container) return;
        container.innerHTML = "";

        ports.forEach(p => {
            let isOffline = p.rx_power_dbm === -99.0 || p.rx_power_dbm < -90.0 || p.status === 'OFFLINE';
            let rxText = isOffline ? "-inf dBm" : `${p.rx_power_dbm} dBm`;
            let rxClass = "text-green";
            let statusText = isOffline ? "OFFLINE" : "ONLINE";
            let statusBadge = isOffline ? "badge-danger" : "badge-success";
            
            if (isOffline) {
                rxClass = "text-danger";
            } else if (p.rx_power_dbm <= -32.0) {
                rxClass = "text-danger";
            } else if (p.rx_power_dbm <= -28.0) {
                rxClass = "text-warning";
            }

            container.innerHTML += `
                <div class="bgp-card glass-panel border-${isOffline ? 'red' : 'green'}">
                    <div class="bgp-header">
                        <span class="bgp-name"><i class="fa-solid fa-plug ${isOffline ? 'text-danger' : 'text-green'}"></i> GPON PORT ${p.port_number}</span>
                        <span class="badge ${statusBadge}">${statusText}</span>
                    </div>
                    <div class="stat-sub-info mt-2">
                        <div><b>Temperatura:</b> ${p.temperature}</div>
                        <div><b>Potência Tx:</b> ${p.tx_power_dbm} dBm</div>
                        <div><b>Potência Rx:</b> <b class="${rxClass}">${rxText}</b></div>
                    </div>
                </div>
            `;
        });
    } catch (err) {
        console.error("Error loading OLT ports:", err);
    }
}

async function loadMikrotikDetails() {
    try {
        const res = await fetch("/api/dashboard/mikrotik");
        const data = await res.json();

        // 1. Render BGP Grid Cards
        const bgpContainer = document.getElementById("bgp-grid-cards");
        bgpContainer.innerHTML = "";
        
        data.bgp_peers.forEach(peer => {
            const isEst = peer.is_established;
            const badgeClass = isEst ? "badge-established" : "badge-down";
            const badgeText = isEst ? "ESTABLISHED" : peer.state.toUpperCase();
            
            const cardHtml = `
                <div class="bgp-card glass-panel border-${isEst ? 'green' : 'red'}">
                    <div class="bgp-header">
                        <span class="bgp-name"><i class="fa-solid fa-server"></i> ${peer.peer_name}</span>
                        <span class="bgp-status-badge ${badgeClass}">${badgeText}</span>
                    </div>
                    <div class="stat-sub-info mt-2">
                        <div><b>IP Remoto:</b> ${peer.remote_address}</div>
                        <div><b>AS Remoto:</b> ${peer.remote_as || 'N/A'}</div>
                        <div><b>Uptime Sessão:</b> ${peer.uptime || 'N/A'}</div>
                    </div>
                </div>
            `;
            bgpContainer.innerHTML += cardHtml;
        });

        // 2. Render RADIUS Status Cards
        const radContainer = document.getElementById("radius-cards");
        if (radContainer) {
            radContainer.innerHTML = "";
            if (!data.radius || data.radius.length === 0) {
                radContainer.innerHTML = `<div class="p-3 text-muted">Nenhum servidor RADIUS cadastrado no MikroTik.</div>`;
            } else {
                data.radius.forEach(rad => {
                    const isUp = rad.status.includes("UP") && !rad.disabled;
                    const hasStats = (rad.requests > 0 || rad.accepts > 0 || rad.rejects > 0);
                    const statsHtml = hasStats 
                        ? `<div><b>Requisições:</b> ${rad.requests} | <b>Aceitas:</b> <b class="text-green">${rad.accepts}</b> | <b>Rejeitadas:</b> <b class="text-danger">${rad.rejects}</b></div>`
                        : `<div><b>Status da Conexão:</b> <b class="text-green"><i class="fa-solid fa-circle-check"></i> Ativo & Operacional</b></div>`;

                    radContainer.innerHTML += `
                        <div class="bgp-card glass-panel border-${isUp ? 'purple' : 'red'}">
                            <div class="bgp-header">
                                <span class="bgp-name"><i class="fa-solid fa-database text-purple"></i> RADIUS (${rad.address})</span>
                                <span class="badge ${isUp ? 'badge-success' : 'badge-danger'}">${rad.status}</span>
                            </div>
                            <div class="stat-sub-info mt-2">
                                <div><b>Serviços Ativos:</b> <code>${rad.service}</code></div>
                                <div><b>Timeout Resposta:</b> ${rad.timeout}</div>
                                ${statsHtml}
                            </div>
                        </div>
                    `;
                });
            }
        }

        // 3. Render Ethernet Interfaces Table
        const ifTable = document.getElementById("interfaces-table");
        if (ifTable) {
            ifTable.innerHTML = "";
            data.interfaces.forEach(item => {
                let badge = `<span class="badge badge-success"><i class="fa-solid fa-link"></i> Link Up (Running)</span>`;
                if (item.disabled) badge = `<span class="badge badge-danger"><i class="fa-solid fa-ban"></i> Desativada</span>`;
                else if (!item.running) badge = `<span class="badge badge-warning"><i class="fa-solid fa-plug-circle-xmark"></i> Link Down</span>`;

                ifTable.innerHTML += `
                    <tr>
                        <td><b><i class="fa-solid fa-ethernet text-blue"></i> ${item.name}</b></td>
                        <td>${badge}</td>
                        <td><code>${item.mac_address || '-'}</code></td>
                        <td><small class="text-muted">${item.comment || '-'}</small></td>
                    </tr>
                `;
            });
        }

        // 4. Render Blocked Clients Table (rbfull_pgcorte)
        const blkTable = document.getElementById("blocked-clients-table");
        const countBlk = document.getElementById("count-blocked-clients");
        if (blkTable) {
            blkTable.innerHTML = "";
            if (countBlk) countBlk.innerText = data.blocked_clients ? data.blocked_clients.length : 0;

            if (!data.blocked_clients || data.blocked_clients.length === 0) {
                blkTable.innerHTML = `<tr><td colspan="5" class="text-center text-muted p-3">Nenhum cliente bloqueado na lista <code>rbfull_pgcorte</code> no momento.</td></tr>`;
            } else {
                data.blocked_clients.forEach(bc => {
                    const isOffline = bc.username.includes("Offline");
                    blkTable.innerHTML += `
                        <tr>
                            <td><b class="${isOffline ? 'text-muted' : 'text-warning'}"><i class="fa-solid fa-user-lock"></i> ${bc.username}</b></td>
                            <td><code>${bc.ip_address}</code></td>
                            <td><small class="text-muted">${bc.mac_address}</small></td>
                            <td><span class="badge badge-info">${bc.uptime}</span></td>
                            <td><code>${bc.list_name}</code></td>
                        </tr>
                    `;
                });
            }
        }

        // 5. Render Top 10 Clients Table
        const clientsTable = document.getElementById("top-clients-table");
        if (clientsTable) {
            clientsTable.innerHTML = "";
            const top10 = (data.top_clients || []).slice(0, 10);
            top10.forEach(client => {
                clientsTable.innerHTML += `
                    <tr>
                        <td><b><i class="fa-solid fa-user-check text-blue"></i> ${client.username}</b></td>
                        <td><code>${client.ip_address}</code></td>
                        <td><small class="text-muted">${client.mac_address}</small></td>
                        <td><span class="badge badge-info">${client.uptime}</span></td>
                    </tr>
                `;
            });
        }

    } catch (err) {
        console.error("Error loading MikroTik details:", err);
    }
}

async function loadONUs() {
    try {
        const res = await fetch("/api/dashboard/onus");
        allOnus = await res.json();
        const countSpan = document.getElementById("count-onu-tab");
        if (countSpan) countSpan.innerText = allOnus.length;
        currentPage = 1;
        renderONUTable();
    } catch (err) {
        console.error("Error loading ONUs:", err);
    }
}

function getFilteredONUs() {
    const searchVal = (document.getElementById("onu-search")?.value || "").toLowerCase().trim();
    const statusVal = document.getElementById("onu-status-filter")?.value || "all";

    return allOnus.filter(onu => {
        const matchesSearch = (onu.name || "").toLowerCase().includes(searchVal) ||
                              (onu.serial || "").toLowerCase().includes(searchVal) ||
                              (onu.slot_port || "").toLowerCase().includes(searchVal) ||
                              (onu.vendor_id || "").toLowerCase().includes(searchVal) ||
                              (onu.model_id || "").toLowerCase().includes(searchVal) ||
                              (onu.ont_version || "").toLowerCase().includes(searchVal) ||
                              (onu.software_version || "").toLowerCase().includes(searchVal);

        if (!matchesSearch) return false;

        if (statusVal === "online") return onu.status === "online";
        if (statusVal === "offline") return onu.status !== "online";
        if (statusVal === "warning") return onu.rx_power < -24.5 && onu.status === "online";
        return true;
    });
}

function onSearchInput() {
    currentPage = 1;
    renderONUTable();
}

function filterONUs() {
    onSearchInput();
}

function changePage(delta) {
    const filtered = getFilteredONUs();
    const totalPages = Math.ceil(filtered.length / PAGE_SIZE) || 1;
    currentPage += delta;
    if (currentPage < 1) currentPage = 1;
    if (currentPage > totalPages) currentPage = totalPages;
    renderONUTable();
}

function renderONUTable() {
    const filtered = getFilteredONUs();
    const totalItems = filtered.length;
    const totalPages = Math.ceil(totalItems / PAGE_SIZE) || 1;

    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIdx = (currentPage - 1) * PAGE_SIZE;
    const endIdx = Math.min(startIdx + PAGE_SIZE, totalItems);
    const pageItems = filtered.slice(startIdx, endIdx);

    const tableBody = document.getElementById("onu-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = "";

    if (pageItems.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="10" class="text-center text-muted py-4">Nenhuma ONU encontrada com os filtros aplicados.</td></tr>`;
    } else {
        pageItems.forEach(onu => {
            let statusBadge = `<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> Online</span>`;
            if (onu.status !== "online") {
                statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-circle-xmark"></i> Offline</span>`;
            }

            let oltRxClass = "text-green";
            if (onu.olt_rx_power < -27.5 || onu.status !== "online") oltRxClass = "text-danger";
            else if (onu.olt_rx_power < -24.5) oltRxClass = "text-warning";

            let onuRxClass = "text-green";
            if (onu.onu_rx_power < -27.5 || onu.status !== "online") onuRxClass = "text-danger";
            else if (onu.onu_rx_power < -24.5) onuRxClass = "text-warning";

            const oltRxText = onu.status === "online" ? `${onu.olt_rx_power} dBm` : "-";
            const onuRxText = onu.status === "online" ? `${onu.onu_rx_power} dBm` : "-";
            const distanceText = onu.status === "online" ? `${onu.distance_km} km` : "-";
            
            let modelVendorText = "";
            if (onu.model_id) {
                modelVendorText = `<b>${onu.model_id}</b>`;
                if (onu.vendor_id) modelVendorText += ` <small class="text-muted">(${onu.vendor_id})</small>`;
            } else if (onu.vendor_id) {
                modelVendorText = `<b>${onu.vendor_id}</b>`;
            }

            if (!modelVendorText && onu.serial && onu.serial.length >= 4) {
                const prefix = onu.serial.substring(0, 4).toUpperCase();
                if (prefix === "ITBS") modelVendorText = "Intelbras (ITBS)";
                else if (prefix === "HWTC") modelVendorText = "Huawei (HWTC)";
                else if (prefix === "ZTEN") modelVendorText = "ZTE (ZTEN)";
                else if (prefix === "VSOL") modelVendorText = "V-SOL (VSOL)";
                else if (prefix === "FHTT") modelVendorText = "FiberHome (FHTT)";
                else if (prefix === "TPLK" || prefix === "TP-L") modelVendorText = "TP-Link (TPLK)";
                else modelVendorText = prefix;
            }

            if (onu.software_version || onu.ont_version) {
                const verText = onu.software_version || onu.ont_version;
                const fullTitle = `Software: ${onu.software_version || '-'} | ONT: ${onu.ont_version || '-'}`;
                modelVendorText += `<br><small class="text-muted" title="${fullTitle}"><i class="fa-solid fa-code-branch"></i> ${verText}</small>`;
            }

            if (!modelVendorText) modelVendorText = "-";

            tableBody.innerHTML += `
                <tr>
                    <td><b>${onu.slot_port}:${onu.onu_id}</b></td>
                    <td><b>${onu.name}</b></td>
                    <td><code>${onu.serial}</code></td>
                    <td><small class="text-muted">${modelVendorText}</small></td>
                    <td>${statusBadge}</td>
                    <td><small>${onu.omci_status}</small></td>
                    <td><b class="${oltRxClass}">${oltRxText}</b></td>
                    <td><b class="${onuRxClass}">${onuRxText}</b></td>
                    <td>${distanceText}</td>
                    <td><small class="text-muted">${onu.uptime}</small></td>
                </tr>
            `;
        });
    }

    // Update Pagination UI
    const pageStartEl = document.getElementById("page-start");
    const pageEndEl = document.getElementById("page-end");
    const totalEl = document.getElementById("total-filtered-onus");
    const pageIndicator = document.getElementById("page-indicator");
    const btnPrev = document.getElementById("btn-prev-page");
    const btnNext = document.getElementById("btn-next-page");

    if (pageStartEl) pageStartEl.textContent = totalItems > 0 ? startIdx + 1 : 0;
    if (pageEndEl) pageEndEl.textContent = endIdx;
    if (totalEl) totalEl.textContent = totalItems;
    if (pageIndicator) pageIndicator.textContent = `Página ${currentPage} de ${totalPages}`;
    if (btnPrev) btnPrev.disabled = currentPage <= 1;
    if (btnNext) btnNext.disabled = currentPage >= totalPages;
}

async function loadHistoryCharts() {
    try {
        const res = await fetch("/api/dashboard/history");
        const data = await res.json();

        const oltLabels = data.olt_history.map(h => h.time);
        const oltOnlineData = data.olt_history.map(h => h.online);
        const oltOfflineData = data.olt_history.map(h => h.offline);

        const mkLabels = data.mikrotik_history.map(m => m.time);
        const mkConnData = data.mikrotik_history.map(m => m.active_connections);

        // OLT Chart
        const ctxOlt = document.getElementById("oltChart").getContext("2d");
        if (oltChart) oltChart.destroy();
        oltChart = new Chart(ctxOlt, {
            type: 'line',
            data: {
                labels: oltLabels,
                datasets: [
                    { label: 'ONUs Online', data: oltOnlineData, borderColor: '#10B981', backgroundColor: 'rgba(16, 185, 129, 0.1)', fill: true, tension: 0.3 },
                    { label: 'ONUs Offline', data: oltOfflineData, borderColor: '#EF4444', backgroundColor: 'rgba(239, 68, 68, 0.1)', fill: true, tension: 0.3 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#9CA3AF' } } },
                scales: {
                    x: { ticks: { color: '#6B7280' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { beginAtZero: true, ticks: { color: '#6B7280' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                }
            }
        });

        // MikroTik Chart
        const ctxMk = document.getElementById("mikrotikChart").getContext("2d");
        if (mikrotikChart) mikrotikChart.destroy();
        mikrotikChart = new Chart(ctxMk, {
            type: 'line',
            data: {
                labels: mkLabels,
                datasets: [
                    { label: 'Conexões PPPoE Ativas', data: mkConnData, borderColor: '#3B82F6', backgroundColor: 'rgba(59, 130, 246, 0.15)', fill: true, tension: 0.3 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#9CA3AF' } } },
                scales: {
                    x: { ticks: { color: '#6B7280' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { beginAtZero: true, ticks: { color: '#6B7280' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                }
            }
        });

    } catch (err) {
        console.error("Error loading charts:", err);
    }
}

// Modal Handlers
async function openSettingsModal() {
    try {
        const res = await fetch("/api/settings");
        const s = await res.json();

        document.getElementById("olt_ip").value = s.olt_ip || "";
        document.getElementById("olt_port").value = s.olt_port || 22;
        document.getElementById("olt_user").value = s.olt_user || "";
        document.getElementById("olt_password").value = s.olt_password || "";
        document.getElementById("olt_interval_minutes").value = s.olt_interval_minutes || 120;
        document.getElementById("olt_command_delay").value = s.olt_command_delay || 0.5;

        document.getElementById("mikrotik_ip").value = s.mikrotik_ip || "";
        document.getElementById("mikrotik_port").value = s.mikrotik_port || 8728;
        document.getElementById("mikrotik_user").value = s.mikrotik_user || "";
        document.getElementById("mikrotik_password").value = s.mikrotik_password || "";
        document.getElementById("mikrotik_interval_minutes").value = s.mikrotik_interval_minutes || 20;
        document.getElementById("mikrotik_drop_threshold").value = s.mikrotik_drop_threshold || 2;

        document.getElementById("telegram_bot_token").value = s.telegram_bot_token || "";
        document.getElementById("telegram_chat_id").value = s.telegram_chat_id || "";
        document.getElementById("telegram_alerts_enabled").checked = s.telegram_alerts_enabled !== false;

        document.getElementById("settings-modal").classList.add("open");
    } catch (err) {
        showToast("Erro ao carregar configurações", "danger");
    }
}

function closeSettingsModal() {
    document.getElementById("settings-modal").classList.remove("open");
}

async function saveSettings(e) {
    e.preventDefault();
    const payload = {
        olt_ip: document.getElementById("olt_ip").value,
        olt_port: parseInt(document.getElementById("olt_port").value),
        olt_user: document.getElementById("olt_user").value,
        olt_password: document.getElementById("olt_password").value,
        olt_interval_minutes: parseInt(document.getElementById("olt_interval_minutes").value),
        olt_command_delay: parseFloat(document.getElementById("olt_command_delay").value),

        mikrotik_ip: document.getElementById("mikrotik_ip").value,
        mikrotik_port: parseInt(document.getElementById("mikrotik_port").value),
        mikrotik_user: document.getElementById("mikrotik_user").value,
        mikrotik_password: document.getElementById("mikrotik_password").value,
        mikrotik_interval_minutes: parseInt(document.getElementById("mikrotik_interval_minutes").value),
        mikrotik_drop_threshold: parseInt(document.getElementById("mikrotik_drop_threshold").value),

        telegram_bot_token: document.getElementById("telegram_bot_token").value,
        telegram_chat_id: document.getElementById("telegram_chat_id").value,
        telegram_alerts_enabled: document.getElementById("telegram_alerts_enabled").checked
    };

    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        showToast(data.message, "success");
        closeSettingsModal();
    } catch (err) {
        showToast("Falha ao salvar configurações", "danger");
    }
}

async function triggerRoutine(type) {
    showToast(`Iniciando rotina do ${type.toUpperCase()}...`, "success");
    try {
        const res = await fetch(`/api/routine/${type}`, { method: "POST" });
        const data = await res.json();
        showToast(data.message, "success");
        await loadSummaryData();
        await loadOLTPorts();
        await loadMikrotikDetails();
        await loadONUs();
    } catch (err) {
        showToast(`Erro ao executar rotina do ${type}`, "danger");
    }
}

async function testTelegramAlert() {
    const token = document.getElementById("telegram_bot_token").value;
    const chat_id = document.getElementById("telegram_chat_id").value;
    if (!token || !chat_id) {
        showToast("Preencha o Token e Chat ID para testar", "danger");
        return;
    }

    try {
        const res = await fetch("/api/telegram/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bot_token: token, chat_id: chat_id })
        });
        const data = await res.json();
        showToast(data.message, data.status === "success" ? "success" : "danger");
    } catch (err) {
        showToast("Erro ao testar envio no Telegram", "danger");
    }
}

function showToast(msg, type) {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fa-solid fa-info-circle"></i> ${msg}`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}
