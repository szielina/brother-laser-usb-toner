# brother-laser-usb-toner

A lightweight, zero-dependency Python utility for querying toner levels and hardware status from USB-only Brother monochrome laser printers under Linux (Raspberry Pi, CUPS print servers, Home Assistant).

---

## The Problem

Budget Brother laser printers (GDI / host-based models driven by `brlaser` or proprietary drivers under CUPS) do not expose supply levels via standard IPP attributes (`marker-levels`).

As a result:
- CUPS reports printer availability, but shows **no toner remaining percentage**.
- Home Assistant's native IPP integration cannot retrieve consumable states.
- Official Brother status utilities are distributed as 32-bit x86 binaries, failing entirely on ARM architectures like Raspberry Pi.

## The Solution

This tool bypasses the spooler and communicates directly with the printer's bidirectional USB character device (`/dev/usb/lpX`) using raw **PJL (Printer Job Language)** and Brother's proprietary maintenance command extension (`BRMAINTENANCE`).

It queries the internal ASIC registers, handles sleep-mode wake-up latency, and parses the hexadecimal consumable payload into standard metrics.

---

## Compatibility

Tested and verified on:
- **Brother HL-1110 / HL-1110E**
- **Brother HL-1112 / HL-1112A**
- **Brother HL-1210W / HL-1212W** (via USB)

*Should work with most Brother monochrome GDI laser printers utilizing the `usblp` kernel driver.*

---

## Prerequisites & Permissions

The script requires **Python 3.6+** (standard library only; no external dependencies).

### Non-Root USB Access (POSIX Standard)
Linux restricts raw character devices (`/dev/usb/lp*`) to `root:lp` ownership. To allow execution without `sudo`, add your user to the standard system printing group:

```bash
sudo usermod -aG lp $USER
```

*Note: Log out and log back in (or restart your shell session) for group membership changes to take effect.*

---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/brother-laser-usb-toner.git
cd brother-laser-usb-toner
chmod +x brother_toner.py
```

---

## CLI Usage

### 1. Default (Single Integer Output)
Ideal for UNIX pipes, cron jobs, and monitoring agents:
```bash
$ ./brother_toner.py
60
```

### 2. JSON Output
Exposes toner percentage, device state string, and standardized PJL code:
```bash
$ ./brother_toner.py --json
{
  "toner": 60,
  "status": "SLEEP",
  "code": 40000
}
```

### 3. Diagnostic / Raw PJL Stream
Dumps the raw stream received from the printer engine:
```bash
$ ./brother_toner.py --raw
```

### 4. Custom Device Path
Specify an alternate printer node:
```bash
$ ./brother_toner.py -d /dev/usb/lp1
```

---

## Protocol Breakdown

### Command Sequence
The host transmits a Universal Exit Language (UEL) escape followed by PJL commands:
```text
\x1b%-12345X@PJL SET NOTIFYBRMAINTENANCE=ON\r\n
@PJL INFO BRMAINTENANCE\r\n
@PJL INFO STATUS\r\n
```

### Consumable Payload (`DATA="81,..."`)
Brother encodes maintenance items in comma-separated hex bytes:
```text
@PJL INFO BRMAINTENANCE
DATA="31,01,04,00,00,00,01"
DATA="81,01,04,00,00,00,3C"
```

- **`31`**: Cartridge presence / drum state flag (`0x01` = Installed / Ready).
- **`81`**: Black Toner Life Remaining identifier.
- **`3C`**: 32-bit big-endian payload in hexadecimal:  
  `0x3C = 60` -> **60% toner remaining**.
- Scale: `0x00` (0%) to `0x64` (100%).

### PJL Status Codes (`CODE`)
The numeric code conforms to HP/Brother PJL specifications:
- `10001`: Ready / Online
- `30000`: Processing / Printing
- `40000`: Power Save / Sleep mode
- `50001`+: User intervention required (Paper out, cover open)
- `60000`+: Hardware / Mechanical fault (Jam)

---

## Home Assistant Integration

You can integrate the printer as a native sensor using the `command_line` integration in your `configuration.yaml`.

### Configuration (Local Container or Remote via SSH)

```yaml
# Home Assistant configuration.yaml
command_line:
  - sensor:
      name: "Brother HL-1110 Toner"
      command: "python3 /config/brother_toner.py --json"
      #command: "ssh -i /config/ssh/id_rsa -o StrictHostKeyChecking=no pi@192.168.1.50 '/home/pi/brother_toner.py --json'"
      value_template: "{{ value_json.toner }}"
      unit_of_measurement: "%"
      state_class: measurement
      scan_interval: 1800 # 30 minutes
      #scan_interval: 86400 # 24h
      icon: mdi:printer-check
      json_attributes:
        - status
        - code
```

This creates:
- Primary sensor state: **`60%`**
- Attributes: `status: "SLEEP"`, `code: 40000`.

---

## Concurrency with CUPS
When CUPS is actively spooling a print job, it claims an exclusive handle on `/dev/usb/lpX`. If this tool queries the printer during physical printing, it will encounter a busy resource. It automatically recovers once the printer returns to `idle` or `sleep`.

---

## License
MIT License. Feel free to modify and distribute.