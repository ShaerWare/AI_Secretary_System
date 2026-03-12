#!/usr/bin/env python3
"""
Quick test: dial into SIM7600E-H, enable PCM, capture raw audio, check for data.

Usage:
  1. Run this script
  2. Call +79992862779 from your phone
  3. Script auto-answers after 2 rings, captures 5 seconds of PCM, reports RMS levels
  4. Ctrl+C to stop

This bypasses the orchestrator — uses AT port directly.
Stop the orchestrator first: kill $(fuser /dev/ttyUSB2 2>/dev/null)
"""

import math
import signal
import struct
import sys
import time

import serial


AT_PORT = "/dev/ttyUSB2"
AUDIO_PORT = "/dev/ttyUSB4"
BAUD = 115200
PCM_FRAME_BYTES = 320  # 20ms at 8kHz 16-bit mono


def at_cmd(ser: serial.Serial, cmd: str, timeout: float = 3.0) -> list[str]:
    """Send AT command, return response lines."""
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r".encode())
    time.sleep(0.1)

    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if line:
            lines.append(line)
            if line in ("OK", "ERROR", "> "):
                break
    print(f"  [{cmd}] -> {lines}")
    return lines


def main():
    print("=== SIM7600E-H PCM Audio Test ===\n")

    # Open AT port
    at = serial.Serial(AT_PORT, BAUD, timeout=1)
    print(f"AT port {AT_PORT} opened")

    # Basic check
    at_cmd(at, "AT")
    at_cmd(at, "AT+CLIP=1")  # Enable caller ID

    # Set PCM format to linear 8kHz
    at_cmd(at, "AT+CPCMFRM=0")

    # Set volume
    at_cmd(at, "AT+CLVL=5")

    print("\n--- Waiting for incoming call (call +79992862779) ---")
    print("    Will auto-answer after 2 RINGs\n")

    ring_count = 0
    call_active = False

    def cleanup(sig=None, frame=None):
        print("\nCleaning up...")
        try:
            at_cmd(at, "AT+CPCMREG=0")
            at_cmd(at, "AT+CHUP")
        except Exception:
            pass
        at.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)

    # Wait for RING
    at.timeout = 30
    while True:
        line = at.readline().decode("utf-8", errors="replace").strip()
        if not line:
            continue
        print(f"  << {line}")

        if "RING" in line:
            ring_count += 1
            print(f"  [RING #{ring_count}]")

            if ring_count >= 2:
                print("\n--- Answering call ---")
                at_cmd(at, "ATA")
                call_active = True
                time.sleep(0.5)
                break

    if not call_active:
        print("No call detected")
        cleanup()
        return

    # Enable PCM
    print("\n--- Enabling PCM audio ---")
    at_cmd(at, "AT+CPCMREG=1")
    time.sleep(0.3)

    # Check PCM status
    at_cmd(at, "AT+CPCMREG?")

    # Open audio port
    print(f"\n--- Opening audio port {AUDIO_PORT} ---")
    try:
        audio = serial.Serial(AUDIO_PORT, BAUD, timeout=0.1, write_timeout=1)
        print(f"Audio port opened: {audio.name}")
    except Exception as e:
        print(f"FAILED to open audio port: {e}")
        cleanup()
        return

    # Read PCM frames for 10 seconds
    print("\n--- Reading PCM audio (10 seconds, speak into phone!) ---\n")
    start = time.time()
    frame_count = 0
    total_bytes = 0
    rms_values = []

    while time.time() - start < 10:
        data = audio.read(PCM_FRAME_BYTES)
        if not data:
            continue

        total_bytes += len(data)
        frame_count += 1

        # Calculate RMS
        if len(data) >= 2:
            samples = struct.unpack(f"<{len(data) // 2}h", data)
            rms = math.sqrt(sum(s * s for s in samples) / len(samples))
            rms_values.append(rms)

            # Print level bar every 10 frames (~200ms)
            if frame_count % 10 == 0:
                bar_len = min(int(rms / 200), 50)
                bar = "#" * bar_len
                elapsed = time.time() - start
                print(f"  {elapsed:5.1f}s | RMS: {rms:7.1f} | {bar}")

    audio.close()

    # Also try writing a tone (1kHz sine at 8kHz sample rate)
    print("\n--- Generating test tone (1kHz, 2 seconds) ---")
    audio = serial.Serial(AUDIO_PORT, BAUD, timeout=0.1, write_timeout=1)
    import math as m

    frames_to_send = int(2.0 / 0.020)  # 2 seconds / 20ms per frame
    for i in range(frames_to_send):
        samples = []
        for j in range(160):  # 160 samples per 20ms frame
            t = (i * 160 + j) / 8000.0
            sample = int(16000 * m.sin(2 * m.pi * 1000 * t))
            samples.append(max(-32768, min(32767, sample)))
        frame = struct.pack(f"<{len(samples)}h", *samples)
        try:
            audio.write(frame)
            time.sleep(0.018)  # slightly less than 20ms for pacing
        except Exception as e:
            print(f"  Write error at frame {i}: {e}")
            break

    print("  Tone sent. Did you hear it on the phone?")
    audio.close()

    # Disable PCM and hang up
    print("\n--- Hanging up ---")
    at_cmd(at, "AT+CPCMREG=0")
    at_cmd(at, "AT+CHUP")
    at.close()

    # Summary
    print("\n=== RESULTS ===")
    print(f"  Frames read:  {frame_count}")
    print(f"  Total bytes:  {total_bytes}")
    if rms_values:
        avg_rms = sum(rms_values) / len(rms_values)
        max_rms = max(rms_values)
        print(f"  Avg RMS:      {avg_rms:.1f}")
        print(f"  Max RMS:      {max_rms:.1f}")
        if max_rms < 50:
            print("\n  ⚠️  Very low audio levels — PCM data may be silence/noise")
            print("     Try: AT+CMIC=0,15 (mic gain) or check audio routing")
        elif max_rms > 500:
            print("\n  ✓  Audio levels look good — speech detected!")
        else:
            print("\n  ~  Low but non-zero — some audio present, may need gain adjustment")
    else:
        print("  ⚠️  NO FRAMES READ — PCM audio port is not delivering data!")
        print("     Possible causes:")
        print("     1. AT+CPCMREG=1 must be sent DURING active call")
        print("     2. Wrong audio port (try other /dev/ttyUSB* ports)")
        print("     3. PCM not supported over USB on this firmware")


if __name__ == "__main__":
    main()
