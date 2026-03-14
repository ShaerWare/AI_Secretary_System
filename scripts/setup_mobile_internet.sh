#!/bin/bash
# Настройка мобильного интернета через SIM7600E-H (QMI)
#
# Использование:
#   sudo bash scripts/setup_mobile_internet.sh start   # Поднять интернет
#   sudo bash scripts/setup_mobile_internet.sh stop    # Отключить
#   sudo bash scripts/setup_mobile_internet.sh status  # Проверить
#
# Требует: libqmi-utils, udhcpc или dhclient

set -euo pipefail

QMI_DEV="/dev/cdc-wdm2"
APN="internet"
IFACE="wwan0"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
log_err()  { echo -e "${RED}[ERR]${NC} $1"; }
log_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_err "Нужен root. Запустите: sudo $0 $1"
        exit 1
    fi
}

find_wwan_iface() {
    # SIM7600 creates wwan0 or similar interface
    for iface in wwan0 wwan1 usb0; do
        if ip link show "$iface" &>/dev/null; then
            IFACE="$iface"
            return 0
        fi
    done
    # Try to find by driver
    for path in /sys/class/net/*/device/driver; do
        if [[ -e "$path" ]] && readlink -f "$path" | grep -q "qmi_wwan\|cdc_ether"; then
            IFACE=$(echo "$path" | cut -d'/' -f5)
            return 0
        fi
    done
    return 1
}

do_start() {
    check_root "start"

    log_info "Поиск QMI устройства..."
    if [[ ! -e "$QMI_DEV" ]]; then
        log_err "QMI устройство $QMI_DEV не найдено"
        exit 1
    fi
    log_ok "QMI: $QMI_DEV"

    log_info "Поиск сетевого интерфейса..."
    if ! find_wwan_iface; then
        log_err "Не найден wwan интерфейс (wwan0/usb0)"
        log_info "Попробуйте: modprobe qmi_wwan"
        exit 1
    fi
    log_ok "Интерфейс: $IFACE"

    # Check if already connected
    if ip addr show "$IFACE" 2>/dev/null | grep -q "inet "; then
        log_info "Интерфейс $IFACE уже имеет IP адрес"
        ip addr show "$IFACE" | grep "inet "
        return 0
    fi

    # Set interface raw IP mode (required for QMI)
    log_info "Настройка raw IP mode..."
    ip link set "$IFACE" down 2>/dev/null || true
    echo Y > "/sys/class/net/$IFACE/qmi/raw_ip" 2>/dev/null || true
    ip link set "$IFACE" up

    # Stop any existing QMI connection
    qmicli -d "$QMI_DEV" --wds-stop-network=disable-autoconnect 2>/dev/null || true

    # Start QMI network connection
    log_info "Подключение к сети (APN: $APN)..."
    OUTPUT=$(qmicli -d "$QMI_DEV" \
        --wds-start-network="apn=$APN,ip-type=4" \
        --client-no-release-cid 2>&1) || {
        log_err "Не удалось подключиться: $OUTPUT"
        exit 1
    }

    # Extract packet data handle
    HANDLE=$(echo "$OUTPUT" | grep -oP 'Packet data handle: \K\d+' || echo "")
    CID=$(echo "$OUTPUT" | grep -oP 'CID: \K\d+' || echo "")
    log_ok "Подключено (handle=$HANDLE, cid=$CID)"

    # Save handle for stop
    echo "$HANDLE:$CID" > /tmp/qmi_connection_info

    # Get IP via DHCP
    log_info "Получение IP адреса (udhcpc/dhclient)..."
    if command -v udhcpc &>/dev/null; then
        udhcpc -i "$IFACE" -f -q -n 2>&1 || {
            log_info "udhcpc не сработал, пробуем через QMI..."
            _get_ip_from_qmi
        }
    elif command -v dhclient &>/dev/null; then
        dhclient -1 "$IFACE" 2>&1 || {
            log_info "dhclient не сработал, пробуем через QMI..."
            _get_ip_from_qmi
        }
    else
        log_info "DHCP клиент не найден, получаем IP через QMI..."
        _get_ip_from_qmi
    fi

    # Verify
    if ip addr show "$IFACE" | grep -q "inet "; then
        IP=$(ip addr show "$IFACE" | grep -oP 'inet \K[\d.]+')
        log_ok "IP адрес: $IP на $IFACE"
    else
        log_err "IP адрес не получен"
        exit 1
    fi

    log_ok "Мобильный интернет активен на $IFACE"
    echo ""
    log_info "Для маршрутизации всего трафика:"
    echo "  sudo ip route add default via $IP dev $IFACE metric 100"
    log_info "Для проверки:"
    echo "  ping -I $IFACE 8.8.8.8"
}

_get_ip_from_qmi() {
    # Get IP settings directly from QMI
    WDS_INFO=$(qmicli -d "$QMI_DEV" --wds-get-current-settings 2>&1) || return 1

    IP=$(echo "$WDS_INFO" | grep -oP 'IPv4 address: \K[\d.]+' || echo "")
    GW=$(echo "$WDS_INFO" | grep -oP 'IPv4 gateway address: \K[\d.]+' || echo "")
    DNS1=$(echo "$WDS_INFO" | grep -oP 'IPv4 primary DNS: \K[\d.]+' || echo "")
    DNS2=$(echo "$WDS_INFO" | grep -oP 'IPv4 secondary DNS: \K[\d.]+' || echo "")
    PREFIX=$(echo "$WDS_INFO" | grep -oP 'IPv4 subnet mask: \K[\d.]+' || echo "255.255.255.0")

    if [[ -z "$IP" ]]; then
        log_err "Не удалось получить IP из QMI"
        return 1
    fi

    # Calculate prefix length from subnet mask
    PREFIXLEN=$(python3 -c "
import ipaddress
print(ipaddress.IPv4Network('0.0.0.0/$PREFIX').prefixlen)
" 2>/dev/null || echo "24")

    ip addr add "$IP/$PREFIXLEN" dev "$IFACE" 2>/dev/null || true

    if [[ -n "$GW" ]]; then
        ip route add default via "$GW" dev "$IFACE" metric 700 2>/dev/null || true
    fi

    # Set DNS
    if [[ -n "$DNS1" ]]; then
        log_info "DNS: $DNS1 ${DNS2:+$DNS2}"
    fi
}

do_stop() {
    check_root "stop"

    log_info "Отключение мобильного интернета..."

    # Read saved connection info
    if [[ -f /tmp/qmi_connection_info ]]; then
        IFS=: read -r HANDLE CID < /tmp/qmi_connection_info
        qmicli -d "$QMI_DEV" \
            --wds-stop-network="$HANDLE" \
            --client-cid="$CID" 2>/dev/null || true
        rm -f /tmp/qmi_connection_info
    else
        qmicli -d "$QMI_DEV" --wds-stop-network=disable-autoconnect 2>/dev/null || true
    fi

    find_wwan_iface 2>/dev/null || true
    ip addr flush dev "$IFACE" 2>/dev/null || true
    ip link set "$IFACE" down 2>/dev/null || true

    log_ok "Мобильный интернет отключен"
}

do_status() {
    echo "=== QMI устройство ==="
    if [[ -e "$QMI_DEV" ]]; then
        log_ok "$QMI_DEV существует"
    else
        log_err "$QMI_DEV не найден"
        return
    fi

    echo ""
    echo "=== Сетевой интерфейс ==="
    if find_wwan_iface; then
        log_ok "Интерфейс: $IFACE"
        ip addr show "$IFACE" 2>/dev/null | grep -E "inet |state "
    else
        log_err "wwan интерфейс не найден"
    fi

    echo ""
    echo "=== QMI статус ==="
    if [[ $EUID -eq 0 ]]; then
        qmicli -d "$QMI_DEV" --wds-get-packet-service-status 2>/dev/null || log_err "QMI запрос не удался"
        echo ""
        qmicli -d "$QMI_DEV" --wds-get-current-settings 2>/dev/null || true
    else
        log_info "Для полного статуса запустите: sudo $0 status"
        # At least show interface info
        if find_wwan_iface; then
            if ip addr show "$IFACE" 2>/dev/null | grep -q "inet "; then
                log_ok "IP есть — интернет вероятно активен"
            else
                log_info "IP нет — интернет не подключен"
            fi
        fi
    fi
}

case "${1:-status}" in
    start)  do_start ;;
    stop)   do_stop ;;
    status) do_status ;;
    *)
        echo "Использование: $0 {start|stop|status}"
        exit 1
        ;;
esac
