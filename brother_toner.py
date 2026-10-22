#!/usr/bin/env python3
"""
Brother GDI Laser Printer USB Status & Toner Level Monitor.

Queries Brother laser printers (e.g., HL-1110, HL-1112, HL-1210 series)
via raw PJL (Printer Job Language) commands over the USB character device.

Protocol details:
- Uses Brother proprietary PJL command: '@PJL SET NOTIFYBRMAINTENANCE=ON'
- Consumable parameter ID 0x81 maps to Black Toner Remaining.
- Value format: 32-bit big-endian integer, scaled 0x00 to 0x64 (0 - 100%).
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, Optional

DEFAULT_DEVICE = "/dev/usb/lp0"

# PJL Query sequence: UEL escape + notification subscription + direct queries
PJL_QUERY = (
    b"\x1b%-12345X@PJL SET NOTIFYBRMAINTENANCE=ON\r\n"
    b"@PJL INFO BRMAINTENANCE\r\n"
    b"@PJL INFO STATUS\r\n"
)

# Regex patterns for parsing Brother PJL response stream
RE_TONER = re.compile(r'DATA="81,01,04,00,00,00,([0-9A-Fa-f]{2})"')
RE_STATUS = re.compile(r'DISPLAY="([^"]*)"')
RE_CODE = re.compile(r'CODE=(\d+)')


def query_printer(device_path: str, retries: int = 15, delay: float = 0.1) -> Dict[str, Any]:
    """
    Sends the PJL query to the printer and reads back the response buffer.

    Includes a retry loop to accommodate printer wake-up latency from Power Save / Sleep mode.
    """
    if not os.path.exists(device_path):
        raise FileNotFoundError(f"Device node '{device_path}' does not exist.")

    if not os.access(device_path, os.R_OK | os.W_OK):
        raise PermissionError(
            f"Insufficient permissions for '{device_path}'. "
            "Ensure the current user belongs to the 'lp' system group."
        )

    raw_response = ""

    with open(device_path, "r+b", buffering=0) as dev:
        dev.write(PJL_QUERY)

        # Polling loop for bidirectional read (allows engine warm-up / wake-up)
        for _ in range(retries):
            time.sleep(delay)
            chunk = dev.read(1024).decode("latin1", errors="ignore")
            if chunk:
                raw_response += chunk
                # Stop as soon as we have received BOTH toner data and device status
                if "DATA=" in raw_response and ("CODE=" in raw_response or "DISPLAY=" in raw_response):
                    break

    # Parse toner remaining percentage
    toner_match = RE_TONER.search(raw_response)
    toner_pct: Optional[int] = int(toner_match.group(1), 16) if toner_match else None

    # Parse device operational status string (e.g., 'READY', 'SLEEP')
    status_match = RE_STATUS.search(raw_response)
    status_str = status_match.group(1).strip() if status_match else "UNKNOWN"

    # Parse PJL status code (e.g., 10001, 40000)
    code_match = RE_CODE.search(raw_response)
    status_code: Optional[int] = int(code_match.group(1)) if code_match else None

    return {
        "toner": toner_pct,
        "status": status_str,
        "code": status_code,
        "raw": raw_response,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query toner level and operational status from Brother USB laser printers."
    )
    parser.add_argument(
        "-d", "--device",
        default=DEFAULT_DEVICE,
        help=f"Path to USB printer character device (default: {DEFAULT_DEVICE})",
    )
    parser.add_argument(
        "-j", "--json",
        action="store_true",
        help="Output full state as JSON",
    )
    parser.add_argument(
        "-r", "--raw",
        action="store_true",
        help="Print raw PJL response stream from device",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        data = query_printer(args.device)
    except (FileNotFoundError, PermissionError) as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(2)
    except Exception as err:
        sys.stderr.write(f"I/O Error: {err}\n")
        sys.exit(1)

    if args.raw:
        sys.stdout.write(data["raw"])
        return

    if args.json:
        # Exclude raw payload from JSON output unless explicitly requested
        payload = {k: v for k, v in data.items() if k != "raw"}
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return

    # Default CLI output: integer percentage to stdout (ideal for shell scripts / UNIX pipes)
    if data["toner"] is not None:
        sys.stdout.write(f"{data['toner']}\n")
    else:
        sys.stderr.write("Warning: Toner level could not be extracted from device response.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
