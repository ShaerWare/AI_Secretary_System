#!/bin/bash
# Мониторинг мобильного интернета SIM7600E-H
#
# Функции:
#   1. Держит wwan0 поднятым (QMI reconnect)
#   2. Переключает маршрут VPN-сервера на wwan0 если WiFi пропал
#   3. Возвращает маршрут на WiFi когда он вернулся
#
# Использование:
#   sudo bash scripts/mobile-internet-monitor.sh
#   # Или как systemd-сервис (см. scripts/mobile-internet.service)

set -uo pipefail

# === Конфигурация ===
QMI_DEV="/dev/cdc-wdm2"
APN="internet"
VPN_SERVER="155.212.231.7"
CHECK_INTERVAL=15        # Секунд между проверками
RECONNECT_COOLDOWN=30    # Секунд между попытками реконнекта QMI
LOG_TAG="mobile-inet"

# === Переменные состояния ===
WWAN_IFACE=""
WIFI_IFACE=""
LAST_RECONNECT=0
VPN_ROUTE_VIA=""  # "wifi" или "wwan" — текущий маршрут до VPN

log() { logger -t "$LOG_TAG" "$1"; echo "$(date '+%H:%M:%S') $1"; }

find_wwan() {
    for iface in wwan0 wwan1 usb0; do
        if ip link show "$iface" &>/dev/null; then
            WWAN_IFACE="$iface"
            return 0
        fi
    done
    return 1
}

find_wifi() {
    # Ищем WiFi интерфейс с IP-адресом
    WIFI_IFACE=""
    for iface in $(ip -br link show type none 2>/dev/null | awk '{print $1}'); do
        if iw dev "$iface" info &>/dev/null 2>&1; then
            if ip addr show "$iface" 2>/dev/null | grep -q "inet "; then
                WIFI_IFACE="$iface"
                return 0
            fi
        fi
    done
    # Fallback: ищем по имени wl*
    for iface in $(ip -br addr show | grep "^wl" | awk '{print $1}'); do
        if ip addr show "$iface" 2>/dev/null | grep -q "inet "; then
            WIFI_IFACE="$iface"
            return 0
        fi
    done
    return 1
}

wwan_has_ip() {
    [[ -n "$WWAN_IFACE" ]] && ip addr show "$WWAN_IFACE" 2>/dev/null | grep -q "inet "
}

wwan_can_ping() {
    [[ -n "$WWAN_IFACE" ]] && ping -I "$WWAN_IFACE" -c 2 -W 5 8.8.8.8 &>/dev/null
}

wifi_gateway() {
    # Возвращает gateway WiFi
    ip route show dev "$WIFI_IFACE" 2>/dev/null | grep default | awk '{print $3}' | head -1
}

wwan_gateway() {
    ip route show dev "$WWAN_IFACE" 2>/dev/null | grep default | awk '{print $3}' | head -1
}

reconnect_qmi() {
    local now
    now=$(date +%s)
    if (( now - LAST_RECONNECT < RECONNECT_COOLDOWN )); then
        return 1
    fi
    LAST_RECONNECT=$now

    log "QMI reconnect: поднимаем wwan0..."

    # Если интерфейс уже UP — не трогаем link, только переподключаем data
    if ! ip link show "$WWAN_IFACE" 2>/dev/null | grep -q "UP"; then
        ip link set "$WWAN_IFACE" down 2>/dev/null || true
        echo Y > "/sys/class/net/$WWAN_IFACE/qmi/raw_ip" 2>/dev/null || true
        ip link set "$WWAN_IFACE" up
    fi

    # Останавливаем старое соединение
    qmicli -d "$QMI_DEV" --wds-stop-network=disable-autoconnect 2>/dev/null || true

    # Подключаемся
    local output
    output=$(qmicli -d "$QMI_DEV" \
        --wds-start-network="apn=$APN,ip-type=4" \
        --client-no-release-cid 2>&1) || {
        log "QMI connect failed: $output"
        return 1
    }

    # Получаем IP через QMI
    sleep 2
    local wds_info ip gw prefix prefixlen
    wds_info=$(qmicli -d "$QMI_DEV" --wds-get-current-settings 2>&1) || return 1

    ip=$(echo "$wds_info" | grep -oP 'IPv4 address: \K[\d.]+')
    gw=$(echo "$wds_info" | grep -oP 'IPv4 gateway address: \K[\d.]+')
    prefix=$(echo "$wds_info" | grep -oP 'IPv4 subnet mask: \K[\d.]+' || echo "255.255.255.0")

    if [[ -z "$ip" ]]; then
        log "QMI: IP не получен"
        return 1
    fi

    prefixlen=$(python3 -c "import ipaddress; print(ipaddress.IPv4Network('0.0.0.0/$prefix').prefixlen)" 2>/dev/null || echo "24")

    ip addr flush dev "$WWAN_IFACE" 2>/dev/null || true
    ip addr add "$ip/$prefixlen" dev "$WWAN_IFACE" 2>/dev/null || true
    if [[ -n "$gw" ]]; then
        ip route add default via "$gw" dev "$WWAN_IFACE" metric 800 2>/dev/null || true
    fi

    log "QMI connected: $ip via $gw on $WWAN_IFACE"
    return 0
}

set_vpn_route_via_wwan() {
    if [[ "$VPN_ROUTE_VIA" == "wwan" ]]; then
        return 0  # Уже через wwan
    fi
    local gw
    gw=$(wwan_gateway)
    if [[ -z "$gw" ]]; then
        log "WARN: нет gateway для wwan, не могу переключить VPN маршрут"
        return 1
    fi

    # Удаляем старый маршрут и ставим через wwan
    ip route del "$VPN_SERVER" 2>/dev/null || true
    ip route add "$VPN_SERVER" via "$gw" dev "$WWAN_IFACE" 2>/dev/null || {
        log "ERR: не удалось добавить маршрут $VPN_SERVER via $gw dev $WWAN_IFACE"
        return 1
    }

    VPN_ROUTE_VIA="wwan"
    log "VPN маршрут → wwan0 ($gw)"
}

set_vpn_route_via_wifi() {
    if [[ "$VPN_ROUTE_VIA" == "wifi" ]]; then
        return 0
    fi
    local gw
    gw=$(wifi_gateway)
    if [[ -z "$gw" ]]; then
        return 1
    fi

    ip route del "$VPN_SERVER" 2>/dev/null || true
    ip route add "$VPN_SERVER" via "$gw" dev "$WIFI_IFACE" 2>/dev/null || {
        return 1
    }

    VPN_ROUTE_VIA="wifi"
    log "VPN маршрут → WiFi ($gw)"
}

detect_current_vpn_route() {
    local route
    route=$(ip route show "$VPN_SERVER" 2>/dev/null)
    if echo "$route" | grep -q "$WWAN_IFACE" 2>/dev/null; then
        VPN_ROUTE_VIA="wwan"
    elif [[ -n "$WIFI_IFACE" ]] && echo "$route" | grep -q "$WIFI_IFACE" 2>/dev/null; then
        VPN_ROUTE_VIA="wifi"
    else
        VPN_ROUTE_VIA="unknown"
    fi
}

# === Main loop ===
log "Запуск монитора мобильного интернета"
log "QMI: $QMI_DEV, APN: $APN, VPN: $VPN_SERVER"

if [[ $EUID -ne 0 ]]; then
    log "WARN: запущен без root — переключение маршрутов не будет работать"
fi

while true; do
    find_wwan || { log "wwan интерфейс не найден"; sleep "$CHECK_INTERVAL"; continue; }
    find_wifi  # WiFi может отсутствовать — это нормально

    detect_current_vpn_route

    # 1. Проверяем wwan0
    if ! wwan_has_ip; then
        log "wwan0 без IP — пробуем переподключить QMI"
        reconnect_qmi && sleep 5  # Даём время на установку соединения
    fi

    # 2. Проверяем connectivity (только если есть IP)
    WWAN_ONLINE=false
    if wwan_has_ip; then
        if wwan_can_ping; then
            WWAN_ONLINE=true
        else
            log "wwan0 имеет IP но не пингует — пробуем реконнект"
            reconnect_qmi && sleep 5
            # Повторная проверка после реконнекта
            wwan_can_ping && WWAN_ONLINE=true
        fi
    fi

    # 3. Логика маршрутизации VPN
    if find_wifi; then
        # WiFi есть — VPN через WiFi (приоритетнее)
        set_vpn_route_via_wifi
    elif $WWAN_ONLINE; then
        # WiFi нет, wwan работает — VPN через wwan
        set_vpn_route_via_wwan
    else
        log "WARN: ни WiFi ни wwan не доступны для VPN"
    fi

    sleep "$CHECK_INTERVAL"
done
