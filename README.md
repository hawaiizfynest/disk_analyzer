# 🗂️ DiskAnalyzer

A lightweight Windows GUI app that shows you **exactly** what's eating your disk space — with a live treemap, sortable table, and one-click Explorer navigation.

![Python](https://img.shields.io/badge/Python-3.7%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)
![Dependencies](https://img.shields.io/badge/Dependencies-None-brightgreen)

---

## Screenshot

```
┌─────────────────────────────────────────────────────┐
│  DISK ANALYZER                          [▶ SCAN C:\] │
│  PATH: C:\  TOTAL: 500GB  USED: 347GB  FREE: 153GB  │
├─────────────────────────────────────────────────────┤
│  [====== Treemap: visual blocks by size ============]│
├─────────────────────────────────────────────────────┤
│  PATH                    SIZE    % USED  ITEMS  TYPE │
│  C:\Users\AppData\Local  67.4 GB  19.4%  203k  Cache│
│  C:\Program Files        52.1 GB  15.0%   98k  Apps │
│  C:\Users\Downloads      48.2 GB  13.9%    1k  User │
│  C:\Windows              28.4 GB   8.2%  142k  Sys  │
│  ...                                                 │
└─────────────────────────────────────────────────────┘
```

## Features

### 💾 Disk Space Tab
- **Real-time scan** — walks any drive or folder recursively, showing progress as it goes
- **Interactive treemap** — proportional visual blocks; hover for details, click to highlight
- **Sortable table** — click any column to sort by size, name, type, or item count
- **Color-coded types** — System 🔴, Apps 🔵, User Data 🟢, Cache 🟡
- **Filter box** — instantly filter results by path or type
- **Explorer integration** — double-click any row to open it in Windows Explorer
- **Right-click menu** — copy path or open in Explorer
- **Stop button** — abort a scan at any time

### 📦 Installed Programs Tab
- **Registry scan** — reads all installed programs from the Windows registry
- **Size breakdown** — shows how much space each program uses (where reported)
- **Programs treemap** — visual map of space usage across installed apps
- **Uninstall launcher** — select a program and click Uninstall to launch its uninstaller
- **Sortable** — sort by name, publisher, size, version, or install date
- **Filter** — search by name, publisher, or install location
- **Open location** — double-click to open the program's install folder in Explorer

### General
- **Zero dependencies** — uses only Python's built-in `tkinter` and `winreg`
- **Threaded** — UI never freezes during scanning

## Requirements

- Python 3.7 or newer
- Windows (tkinter is included with the standard Python installer)

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/disk-analyzer.git
cd disk-analyzer
python disk_analyzer.py
```

No `pip install` needed — zero external dependencies.

## Build a Standalone .exe

If you want to share the app without requiring Python:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed disk_analyzer.py
```

The `.exe` will be created in the `dist/` folder. You can run it on any Windows machine.

## Usage

1. Enter a drive or folder path (default: `C:\`) or click **Browse…**
2. Click **▶ SCAN** — the app will scan recursively and show results as they come in
3. Click any **column header** to sort
4. Use the **Filter** box to search by path or type
5. **Double-click** a row to open that folder in Windows Explorer
6. **Right-click** a row to copy its path

> **Tip:** Run as Administrator to scan system-protected directories like `C:\Windows\System32`

## What Each Type Means

| Color | Type   | Examples |
|-------|--------|---------|
| 🔴 Red    | System | `C:\Windows`, `pagefile.sys`, `hiberfil.sys` |
| 🔵 Blue   | Apps   | `C:\Program Files`, `C:\ProgramData` |
| 🟢 Green  | User   | `C:\Users\You\Documents`, `Downloads`, `Videos` |
| 🟡 Yellow | Cache  | `AppData\Local`, `AppData\Roaming` |
| ⚪ Grey   | Other  | Everything else |

## Common Space Hogs

| Location | Why it's large | Safe to clean? |
|----------|---------------|----------------|
| `AppData\Local` | App caches, Electron apps, browser data | Partially — check first |
| `Downloads` | Forgotten downloads | Usually yes |
| `hiberfil.sys` | Hibernation file (RAM snapshot) | Yes — run `powercfg /h off` |
| `pagefile.sys` | Virtual memory | No — Windows needs it |
| `$Recycle.Bin` | Deleted files not yet emptied | Yes — empty the Recycle Bin |

## Project Structure

```
disk-analyzer/
├── disk_analyzer.py   # Main application (single file)
├── README.md
├── LICENSE
└── .gitignore
```

## Contributing

Pull requests are welcome! Some ideas for future improvements:

- [ ] Recursive drill-down (click a folder to scan inside it)
- [ ] File type breakdown (images, videos, docs, etc.)
- [ ] Export results to CSV
- [ ] "Largest files" view (not just folders)
- [ ] macOS / Linux support

## License

MIT — see [LICENSE](LICENSE) for details.
