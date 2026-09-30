# iPhone Sysdiagnose Inspector

Extract and summarize battery, display, RAM, storage, and regional details from an iPhone sysdiagnose archive.

This project is designed to read common files from an extracted iPhone sysdiagnose and report useful device information in a simple, human-readable format or machine-readable JSON.

## What this script can inspect

- Battery information
- Display supplier and panel metadata
- RAM size and vendor details
- Storage controller, NAND type, cell count, chip ID, and status
- Wi-Fi module vendor when reported by IORegistry
- Modem chipset, version, and PCI identifiers when reported by IORegistry
- Sales region / market group hints
- Model-specific sourcing notes for supported devices

## Requirements

- Python 3.9 or newer
- An extracted iPhone sysdiagnose directory

No external dependencies are required.

## Download

You can download the latest version from GitHub:

- https://github.com/ThatLastGamer/iPhone-sysdiagnose-parser

Or clone it with Git:

```bash
git clone https://github.com/ThatLastGamer/iPhone-sysdiagnose-parser.git
cd iPhone-sysdiagnose-parser
```

## Install Python

### macOS

If you do not already have Python installed, install it from Python.org or with Homebrew:

```bash
brew install python
```

### Linux

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3
```

On Fedora/RHEL:

```bash
sudo dnf install python3
```

### Windows

Download and install Python from:

https://www.python.org/downloads/windows/

During installation, make sure the box for "Add Python to PATH" is checked.

## Run the script

From the project directory:

### macOS / Linux

```bash
python3 sysdiagnose_inspect.py /path/to/extracted/sysdiagnose
```

### Windows

```powershell
py sysdiagnose_inspect.py "C:\path\to\extracted\sysdiagnose"
```

## Example usage

### Human-readable output

```bash
python3 sysdiagnose_inspect.py /Users/you/Desktop/iphone_sysdiagnose
```

### JSON output

```bash
python3 sysdiagnose_inspect.py /Users/you/Desktop/iphone_sysdiagnose --json
```

### Select only specific sections

```bash
python3 sysdiagnose_inspect.py /Users/you/Desktop/iphone_sysdiagnose --only battery display storage
```

### Windows example

```powershell
py sysdiagnose_inspect.py "C:\Users\you\Desktop\iphone_sysdiagnose" --json
```

## Output format

The script prints the selected sections and their extracted values. With `--json`, it prints a JSON object containing the same data.

Example:

```json
{
  "battery": {
    "available": true,
    "sampled_at": "2026-09-28T10:21:30",
    "cycle_count": 123,
    "maximum_capacity_percent": 88
  }
}
```

## Important notes

- This script inspects files that are already extracted from an iPhone sysdiagnose bundle.
- It does not collect logs on its own.
- Some values are inferred from community-documented patterns and may not be definitive proof of the original device configuration.
- Always treat model-specific supply-chain metadata as informational, not as guaranteed component verification.

## Troubleshooting

### Python command is not recognized

Try:

```bash
python --version
python3 --version
```

If only `python3` works, use `python3` instead of `python`.

### Script says the directory is not a valid sysdiagnose

Make sure the path you pass is the extracted sysdiagnose folder, not a single file. The folder should contain logs or ioreg information similar to a normal Apple sysdiagnose extraction.

### Some sections come back as unavailable

This usually means the relevant file or key was not present in that extraction. The script is designed to report missing data gracefully rather than failing completely.

## License

This project is released under the MIT License.

## Disclaimer

This project is intended for educational and technical analysis use. It is not an official Apple tool and no hardware or software guarantee is implied.

---

If you want to contribute or improve the parser, open an issue or submit a pull request on GitHub.
