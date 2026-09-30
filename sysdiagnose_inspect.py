#!/usr/bin/env python3
"""Summarize selected hardware details from an extracted iPhone sysdiagnose."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


DISPLAY_SUPPLIERS = {
    "G9N": "Samsung Display",
    "G9P": "Samsung Display",
    "G9Q": "Samsung Display",
    "G9C": "LG Display",
    "GH3": "LG Display",
    "GVC": "LG Display",
    "GVH": "LG Display",
    "J5V": "BOE",
}

REGION_MARKETS = {
    "ZD": [
        "Austria",
        "Belgium",
        "France",
        "Germany",
        "Luxembourg",
        "Monaco",
        "Netherlands",
        "Switzerland",
        "United Kingdom",
    ],
}

MODEL_SOURCING_REPORTS: dict[str, dict[str, Any]] = {
    "iPhone 18 Pro": {
        "display": {
            "reported_suppliers": ["Samsung Display", "LG Display"],
            "status": "Reported qualified suppliers; does not identify the panel in a specific phone.",
            "source": "https://www.macrumors.com/2026/05/06/iphone-18-pro-ltpo-display-upgrade-samsung/",
        },
        "storage": {
            "reported_by_capacity": {
                "256GB and 512GB": {
                    "nand_type": "TLC",
                    "reported_suppliers": ["SK hynix", "Kioxia", "SanDisk"],
                },
                "1TB": {
                    "nand_type": "Primarily QLC; TLC alternative also reported",
                    "reported_suppliers": ["SK hynix", "Samsung (TLC alternative)"],
                },
                "2TB": {
                    "nand_type": "QLC",
                    "reported_suppliers": ["SK hynix"],
                },
            },
            "status": "Unconfirmed supply-chain report attributed to tipster Reptalica; not an identification of this unit.",
            "source": "https://wccftech.com/apple-is-swapping-the-faster-tlc-for-slower-qlc-storage-in-iphone-18-pro-duos-1tb-and-2tb-models-while-charging-sky-high-prices/",
        },
        "checked_at": "2026-09-28",
    },
}


def latest_csv_row(directory: Path, pattern: str) -> dict[str, str] | None:
    latest: tuple[datetime, dict[str, str]] | None = None
    for csv_path in directory.glob(pattern):
        try:
            with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
                for row in csv.DictReader(stream):
                    timestamp = row.get("TimeStamp", "")
                    try:
                        parsed_timestamp = datetime.fromisoformat(timestamp)
                    except ValueError:
                        continue
                    if latest is None or parsed_timestamp > latest[0]:
                        latest = (parsed_timestamp, row)
        except OSError:
            continue
    return latest[1] if latest else None


def earliest_csv_timestamp(directory: Path, pattern: str) -> str | None:
    earliest: datetime | None = None
    for csv_path in directory.glob(pattern):
        try:
            with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
                for row in csv.DictReader(stream):
                    try:
                        timestamp = datetime.fromisoformat(row.get("TimeStamp", ""))
                    except ValueError:
                        continue
                    if earliest is None or timestamp < earliest:
                        earliest = timestamp
        except OSError:
            continue
    return earliest.isoformat(sep=" ") if earliest else None


def parse_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def extract_battery(root: Path) -> dict[str, Any]:
    bdc_dir = root / "logs" / "BatteryBDC"
    daily = latest_csv_row(bdc_dir, "BDC_Daily*.csv")
    once = latest_csv_row(bdc_dir, "BDC_Once*.csv")
    if daily is None:
        return {"available": False, "reason": "No readable BatteryBDC daily records found."}

    design_capacity = parse_int((once or {}).get("DesignCapacity"))
    nominal_capacity = parse_int(daily.get("NominalChargeCapacity"))
    max_capacity = parse_int(daily.get("MaxCapacityPercent"))
    estimated_capacity = None
    if nominal_capacity is not None and design_capacity:
        estimated_capacity = round(nominal_capacity / design_capacity * 100, 1)

    return {
        "available": True,
        "sampled_at": daily.get("TimeStamp"),
        "cycle_count": parse_int(daily.get("CycleCount")),
        "maximum_capacity_percent": max_capacity,
        "nominal_charge_capacity_mAh": nominal_capacity,
        "design_capacity_mAh": design_capacity,
        "estimated_capacity_percent_of_design": estimated_capacity,
    }


def read_first_available(root: Path, relative_paths: tuple[str, ...]) -> tuple[str, str] | None:
    for relative_path in relative_paths:
        path = root / relative_path
        try:
            return relative_path, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return None


def property_string(text: str, key: str) -> str | None:
    pattern = re.compile(rf'"{re.escape(key)}"\s*=\s*<"([^"]*)">')
    match = pattern.search(text)
    return match.group(1) if match else None


def property_string_value(text: str, key: str) -> str | None:
    pattern = re.compile(
        rf'"{re.escape(key)}"\s*=\s*(?:<"([^"]*)">|"([^"]*)")', re.I
    )
    match = pattern.search(text)
    if match is None:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def property_hex(text: str, key: str) -> bytes | None:
    pattern = re.compile(rf'"{re.escape(key)}"\s*=\s*<([0-9a-fA-F]+)>')
    match = pattern.search(text)
    if match is None:
        return None
    try:
        return bytes.fromhex(match.group(1))
    except ValueError:
        return None


def decode_ascii_property(text: str, key: str) -> str | None:
    value = property_hex(text, key)
    if value is None:
        return None
    decoded = value.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()
    return decoded or None


def read_ioreg_sources(root: Path) -> list[tuple[str, str]]:
    sources = []
    for relative_path in (
        "ioreg/IODeviceTree.txt",
        "ioreg/IOService.txt",
        "ioreg/IOPower.txt",
    ):
        try:
            sources.append(
                (relative_path, (root / relative_path).read_text(encoding="utf-8", errors="replace"))
            )
        except OSError:
            continue
    return sources


def registry_node_text(text: str, node_fragment: str) -> str | None:
    node_pattern = re.compile(r"^\s*(?P<prefix>(?:\|\s*)*)\+-o\s+(?P<name>\S+)")
    lines = text.splitlines()
    matching_nodes = []
    for index, line in enumerate(lines):
        match = node_pattern.match(line)
        if match is None or node_fragment.casefold() not in match.group("name").casefold():
            continue

        node_depth = match.group("prefix").count("|")
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            next_match = node_pattern.match(lines[next_index])
            if next_match and next_match.group("prefix").count("|") <= node_depth:
                end = next_index
                break
        matching_nodes.append("\n".join(lines[index:end]))
    return max(matching_nodes, key=len) if matching_nodes else None


def extract_display(root: Path) -> dict[str, Any]:
    source = read_first_available(
        root,
        ("ioreg/IODeviceTree.txt", "ioreg/IOService.txt", "ioreg/IOPower.txt"),
    )
    if source is None:
        return {"available": False, "reason": "No readable IORegistry dump found."}

    relative_path, text = source
    raw_serial = property_string(text, "raw-panel-serial-number")
    if not raw_serial:
        return {"available": False, "reason": "No raw panel serial property found."}

    prefix = raw_serial[:3].upper()
    return {
        "available": True,
        "device_model": property_string(text, "product-description"),
        "supplier_prefix": prefix,
        "panel_supplier": DISPLAY_SUPPLIERS.get(prefix, "Unknown from available prefix map"),
        "mapping_note": "Supplier mapping is community-documented, not an Apple-published decoder.",
        "source": relative_path,
    }


def extract_sales_region(root: Path) -> dict[str, Any]:
    source = read_first_available(
        root,
        ("ioreg/IODeviceTree.txt", "ioreg/IOService.txt", "ioreg/IOPower.txt"),
    )
    if source is None:
        return {"available": False, "reason": "No readable IORegistry dump found."}

    relative_path, text = source
    region_info = decode_ascii_property(text, "region-info")
    regulatory_model = decode_ascii_property(text, "regulatory-model-number")
    model_number = decode_ascii_property(text, "model-number")
    if region_info is None and regulatory_model is None and model_number is None:
        return {"available": False, "reason": "No region or model-number properties found."}

    region_code = region_info.split("/", 1)[0] if region_info else None
    return {
        "available": True,
        "device_model": property_string(text, "product-description"),
        "region_info": region_info,
        "region_code": region_code,
        "reported_market_group": REGION_MARKETS.get(region_code or ""),
        "regulatory_model_number": regulatory_model,
        "model_number": model_number,
        "interpretation_note": "Region-code market lists are unofficial and can vary by product generation; this indicates a target market group, not proof of the original sale location.",
        "region_code_reference": "https://theapplewiki.com/wiki/Model_Regions",
        "source": relative_path,
    }


def extract_ram(root: Path) -> dict[str, Any]:
    source = read_first_available(
        root,
        ("ioreg/IODeviceTree.txt", "ioreg/IOService.txt", "ioreg/IOPower.txt"),
    )
    if source is None:
        return {"available": False, "reason": "No readable IORegistry dump found."}

    relative_path, text = source
    size_data = property_hex(text, "dram-size")
    if size_data is None:
        return {"available": False, "reason": "No DRAM size property found."}

    capacity_bytes = int.from_bytes(size_data, byteorder="little")
    vendor_data = property_hex(text, "dram-vendor")
    vendor = None
    if vendor_data:
        vendor = vendor_data.split(b"\0", 1)[0].decode("ascii", errors="replace") or None

    return {
        "available": True,
        "dram_type": property_string(text, "dram-type"),
        "dram_vendor": vendor,
        "capacity_GiB": round(capacity_bytes / (1024 ** 3), 1),
        "capacity_GB_decimal": round(capacity_bytes / 1_000_000_000, 1),
        "source": relative_path,
    }


def extract_storage(root: Path) -> dict[str, Any]:
    source = read_first_available(
        root,
        ("ioreg/IODeviceTree.txt", "ioreg/IOService.txt", "ioreg/IOPower.txt"),
    )
    if source is None:
        return {"available": False, "reason": "No readable IORegistry dump found."}

    relative_path, text = source
    characteristics_match = re.search(
        r'"Controller Characteristics"\s*=\s*\{([^}]*)\}', text
    )
    if not characteristics_match:
        return {"available": False, "reason": "No storage controller characteristics found."}

    characteristics = characteristics_match.group(1)

    def field_string(key: str) -> str | None:
        match = re.search(rf'"{re.escape(key)}"\s*=\s*"([^"]*)"', characteristics)
        return match.group(1).strip() if match else None

    def field_int(key: str) -> int | None:
        match = re.search(rf'"{re.escape(key)}"\s*=\s*(\d+)', characteristics)
        return int(match.group(1)) if match else None

    marketing_name = field_string("nand-marketing-name")
    bits_per_cell = field_int("default-bits-per-cell")
    nand_type_match = re.search(r"(?:^|[^a-z])(slc|mlc|tlc|qlc)(?:_|$)", marketing_name or "", re.I)
    nand_type = nand_type_match.group(1).upper() if nand_type_match else None
    if nand_type is None:
        nand_type = {1: "SLC", 2: "MLC", 3: "TLC", 4: "QLC"}.get(bits_per_cell)

    capacity_bytes = field_int("capacity")
    model_match = re.search(r'"Model Number"\s*=\s*"([^"]*)"', text)
    return {
        "available": True,
        "ssd_model": model_match.group(1) if model_match else None,
        "capacity_GB_decimal": round(capacity_bytes / 1_000_000_000, 1) if capacity_bytes else None,
        "nand_vendor": field_string("vendor-name"),
        "nand_type": nand_type,
        "bits_per_cell": bits_per_cell,
        "cell_type": field_int("cell-type"),
        "chip_id": field_string("chip-id"),
        "nand_marketing_name": marketing_name,
        "nand_status": property_string_value(text, "AppleNANDStatus"),
        "source": relative_path,
    }


def extract_wifi(root: Path) -> dict[str, Any]:
    sources = read_ioreg_sources(root)
    if not sources:
        return {"available": False, "reason": "No readable IORegistry dump found."}

    for key in ("witi_module_vendor", "ModuleVendor"):
        for relative_path, text in sources:
            module_vendor = property_string_value(text, key)
            if module_vendor:
                return {
                    "available": True,
                    "module_vendor": module_vendor,
                    "matched_property": key,
                    "source": relative_path,
                }

    return {
        "available": False,
        "reason": "No Wi-Fi module vendor property found.",
        "source": [relative_path for relative_path, _ in sources],
    }


def extract_modem(root: Path) -> dict[str, Any]:
    sources = read_ioreg_sources(root)
    if not sources:
        return {"available": False, "reason": "No readable IORegistry dump found."}

    chipset = None
    version = None
    pci_node = None
    pci_source = None
    for relative_path, text in sources:
        chipset = chipset or property_string(text, "baseband-chipset")
        version = version or property_string_value(text, "baseband Version")
        version = version or property_string_value(text, "baseband-version")
        if pci_node is None:
            pci_node = registry_node_text(text, "baseband-pcie")
            if pci_node is not None:
                pci_source = relative_path

    vendor_bytes = property_hex(pci_node or "", "vendor-id")
    vendor_value = property_string_value(pci_node or "", "vendor-id")
    if vendor_bytes:
        vendor_value = f"0x{int.from_bytes(vendor_bytes, byteorder='little'):04x}"
    io_name = property_string_value(pci_node or "", "IOName")

    if not any((chipset, version, vendor_value, io_name)):
        return {"available": False, "reason": "No modem properties found in IORegistry."}

    return {
        "available": True,
        "chipset": chipset,
        "version": version,
        "vendor_id": vendor_value,
        "io_name": io_name,
        "source": pci_source or sources[0][0],
    }


def extract_model_sourcing(root: Path) -> dict[str, Any]:
    source = read_first_available(
        root,
        ("ioreg/IODeviceTree.txt", "ioreg/IOService.txt", "ioreg/IOPower.txt"),
    )
    if source is None:
        return {"available": False, "reason": "No readable IORegistry dump found."}

    relative_path, text = source
    model = property_string(text, "product-description")
    model_identifier = (
        property_string(text, "sub-product-type")
        or property_string(text, "fdr-product-type")
    )
    report = MODEL_SOURCING_REPORTS.get(model or "")
    if report is None:
        return {
            "available": False,
            "device_model": model,
            "device_model_identifier": model_identifier,
            "reason": "No model-specific sourcing report is configured; the internal model identifier is still reported.",
        }

    return {
        "available": True,
        "device_model": model,
        "device_model_identifier": model_identifier,
        "note": "Market reports are not proof of the components installed in this unit; use display and storage sections for per-device readings.",
        "reports": report,
        "device_info_source": relative_path,
    }


def extract_dates(root: Path) -> dict[str, Any]:
    activation_dir = root / "logs" / "MobileActivation"
    activation_pattern = re.compile(
        r"^(\w{3} \w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2} \d{4}).*?"
        r"Activation State: (Activated|Unactivated|Deactivated)"
    )
    activation_events: list[tuple[datetime, str]] = []
    for log_path in activation_dir.glob("mobileactivationd.log*"):
        try:
            with log_path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    match = activation_pattern.search(line)
                    if match is None:
                        continue
                    try:
                        timestamp = datetime.strptime(match.group(1), "%a %b %d %H:%M:%S %Y")
                    except ValueError:
                        continue
                    activation_events.append((timestamp, match.group(2)))
        except OSError:
            continue

    activated_events = [timestamp for timestamp, state in activation_events if state == "Activated"]
    latest_state = max(activation_events, default=(None, None), key=lambda event: event[0] or datetime.min)
    first_battery_record = earliest_csv_timestamp(root / "logs" / "BatteryBDC", "BDC_Once*.csv")

    return {
        "manufacture_date": None,
        "manufacture_date_reason": "No reliable whole-device manufacture date was found. Battery YWW metadata is not a verified device assembly date.",
        "activation_status": latest_state[1],
        "earliest_observed_activated_at": min(activated_events).isoformat(sep=" ") if activated_events else None,
        "activation_date_note": "This is the earliest activation event retained in the logs, not necessarily the original activation date.",
        "earliest_battery_metadata_record_at": first_battery_record,
        "battery_record_date_note": "This is when a battery metadata record was logged; it is not the phone manufacture date.",
    }


# Add future extractors here; --only choices and output sections follow this registry.
PARSERS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "battery": extract_battery,
    "display": extract_display,
    "ram": extract_ram,
    "sales_region": extract_sales_region,
    "storage": extract_storage,
    "wifi": extract_wifi,
    "modem": extract_modem,
    "sourcing": extract_model_sourcing,
    # "dates": extract_dates,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract battery, display, and storage details from an extracted sysdiagnose."
    )
    parser.add_argument(
        "sysdiagnose",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Path to the extracted sysdiagnose directory (default: current directory)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=tuple(PARSERS),
        help="Extract only the named sections (default: all sections)",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    if not args.sysdiagnose.is_dir():
        parser.error(f"not an extracted sysdiagnose directory: {args.sysdiagnose}")

    selected = args.only or list(PARSERS)
    report = {name: PARSERS[name](args.sysdiagnose) for name in selected}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for section, values in report.items():
            print(f"{section.title()}:")
            for key, value in values.items():
                print(f"  {key.replace('_', ' ')}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())