# Batch Folder Sorter

Batch Folder Sorter is a desktop helper app for preparing ingest folders from CSV metadata.

It is intended as a helper tool for working with the meemoo instroom tool workflow.

It is meant for people who need to sort large batches of files into a clean folder structure before ingest, archiving, delivery, or internal review, without having to do the folder work manually.

## Why This Tool Exists

When file batches arrive, they are often:

- mixed together in one folder
- inconsistently named
- partially matching the metadata
- full of files that do not belong in the final ingest structure

Batch Folder Sorter helps turn that messy starting point into a structured output that is easier to review and ingest.

## Important

This app is a helper tool, not a replacement for collection review or ingest quality control.

Please keep in mind:

- this tool modifies file structures (creates folders and moves files), so if you are unsure, please use it on a copy of your data
- always work on a copy of your source material when possible
- always review the output before final ingest or delivery
- unmatched files may be moved to `_EXTRA_FILES`, so they still need human review
- `Undo` restores only the last successful batch action

## What The App Does

The app takes:

- a `ROOT` folder with files
- a CSV file with a `Mapnaam` column

It then matches files to the identifiers in the CSV and moves them into the correct folders automatically.

Files that do not match are moved into `_EXTRA_FILES` instead of being mixed into the main structure.

## Workflows

### Standard Mode

Use this when filenames directly match the values in the CSV.

Example:

```text
CSV Mapnaam: ITEM_001
File: ITEM_001.jpg
```

Output:

```text
ROOT/
  ITEM_001/
    jpg/
      ITEM_001.jpg
```

### Artwork Batch Mode

Use this for artwork-style batches where the filename contains:

- an IE identifier
- a sequence number
- a master suffix like `_M`

Example:

```text
OBJ001_001+FO+FDP_M.tif
OBJ001_001+FO+FDP_B.tif
OBJ001_002+FO+FDP.tif
```

Output:

```text
ROOT/
  OBJ001/
    Masters_16bit/
      OBJ001_001+FO+FDP_M.tif
    Bewerkt_8bit/
      OBJ001_001+FO+FDP_B.tif
      OBJ001_002+FO+FDP.tif
```

Notes:

- `Artwork batch mode` keeps the original filenames
- `_M` is treated as master
- `_B` and files without a suffix go to `Bewerkt_8bit`
- IE identifiers that contain dashes, such as `2814-001`, are supported when that exact value exists in the CSV

## Main Features

- Clean desktop interface
- Standard mode and artwork batch mode
- CSV validation before processing
- `_EXTRA_FILES` handling for unmatched files
- `Undo` for the last successful batch
- Release downloads for macOS and Windows

## Downloads

Download the latest release from:

- [GitHub Releases](https://github.com/viaacode/batch-folder-sorter/releases)

Choose the file that matches your system:

- `BatchFolderSorter-macos-arm64.zip`  
  For Apple Silicon Macs (`M1`, `M2`, `M3`, `M4`)
- `BatchFolderSorter-macos-x86_64.zip`  
  For Intel Macs
- `BatchFolderSorter-windows-x64.zip`  
  For 64-bit Windows systems
- `checksums.txt`  
  SHA256 checksums for release verification

## First Launch

### macOS

1. Download the correct macOS zip.
2. Unzip it.
3. Move `BatchFolderSorter.app` to `Applications` if desired.
4. Open the app.
5. If macOS blocks it on first launch:
   Open `System Settings -> Privacy & Security` and allow the app to run.

Note:

- The app is not notarized yet, so the first launch may require manual confirmation in macOS.

### Windows

1. Download `BatchFolderSorter-windows-x64.zip`.
2. Unzip it.
3. Open the extracted `BatchFolderSorter` folder.
4. Run the application executable.

If Windows SmartScreen appears, continue only if you trust the release source.

## How To Use

1. Open the app.
2. Choose the `ROOT` folder.
3. Choose the CSV file.
4. Select `Standard mode` or `Artwork batch mode`.
5. Click `Run Batch`.
6. Review the result in the `Status` area.
7. If needed, click `Undo` to restore the last successful batch.

## CSV Requirements

The CSV must contain a `Mapnaam` column.

Example:

```csv
Mapnaam
OBJ001
OBJ002
OBJ003
```

If the selected CSV does not match the selected `ROOT` folder, the app will stop and show an error instead of moving everything into `_EXTRA_FILES`.

## Hidden macOS Files

Batch Folder Sorter does not create hidden `._*` files.

These files are usually created by macOS as metadata sidecar files, especially when data is copied to or used from external drives that move between macOS and Windows or other non-Apple filesystems.

If these files appear in a batch or in an ingest workflow, they should be handled separately before ingest.

For a practical explanation and cleanup example, see this Apple Community discussion:

- [How do I delete ._ on mac USB file names](https://discussions.apple.com/thread/252896362?sortBy=rank)

## Screenshots

### Standard mode: base structure by extensions

![Image 19-03-2026 at 17 15](https://github.com/user-attachments/assets/5d2b2ce3-c939-4e35-804a-1f7046777df2)

![Image 19-03-2026 at 17 17](https://github.com/user-attachments/assets/24c75d1c-fa40-4bbf-bb78-32bbbd03d089)

![Image 19-03-2026 at 17 18](https://github.com/user-attachments/assets/7e60d95b-16d1-43d8-884f-787d7f2cf0a8)
 
### Artwork batch mode: structure by artwork filenames

![Image 19-03-2026 at 17 19](https://github.com/user-attachments/assets/225b823e-449f-4784-923b-83fcf18ca2d4)

![Image 19-03-2026 at 17 20](https://github.com/user-attachments/assets/7f6f95cd-2b18-4364-836c-ce0aff2ae7e6)

![Image 19-03-2026 at 17 20 (1)](https://github.com/user-attachments/assets/4cb2f6f2-379a-4b52-a22e-ea1200001cd6)

## For Developers

### Requirements

- Python 3.9+

Install dependencies:

```bash
python3 -m venv venv_gui
source venv_gui/bin/activate
pip install -r requirements.txt
```

### Run From Source

```bash
source venv_gui/bin/activate
python gui.py
```

### Build Locally

```bash
source venv_gui/bin/activate
pyinstaller BatchFolderSorter.spec
```

### Automated Builds

GitHub Actions is configured to build release artifacts for:

- `macOS arm64`
- `macOS x86_64`
- `Windows x64`

Manual build workflow:

- Open the `Actions` tab in GitHub
- Run `Build And Release`
- Download the generated artifacts

Tag-based release workflow:

```bash
git tag v1.0.0
git push origin v1.0.0
```

When a tag like `v1.0.0` is pushed, GitHub Actions will:

- build all three platform artifacts
- create or update a GitHub Release
- upload the zip files
- upload `checksums.txt`

## Development Notes

- `Undo` restores the last successful batch only
- The repository ignores local builds, test samples, and virtual environments
