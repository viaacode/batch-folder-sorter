import csv
import re
import shutil
from pathlib import Path

ALLOWED_EXTS = {
    ".ac3", ".aif", ".dng", ".dv", ".flac", ".jp2", ".jpeg", ".jpg",
    ".m4a", ".m4v", ".mkv", ".mov", ".mp2", ".mp3", ".mp4",
    ".mpeg", ".mpg", ".mxf", ".png", ".psb", ".srt",
    ".tif", ".tiff", ".ts", ".wav"
}

EXTRA_DIR_NAME = "_EXTRA_FILES"


ARTWORK_PATTERN = re.compile(r"^(?P<ie>[^_+\-]+)[_-](?P<sequence>\d+)")
ARTWORK_SUFFIX_PATTERN = re.compile(r"^[_-](?P<sequence>\d+)(?:$|[+_-].*)")


def _is_cancelled(stop_event):
    return bool(stop_event and stop_event.is_set())


def _log(logger, message):
    if logger:
        logger(message)
    else:
        print(message)


def parse_csv(csv_path, stop_event=None, logger=None):
    valid_ie_map = {}

    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        _log(logger, f"CSV headers: {reader.fieldnames}")
        if not reader.fieldnames or "Mapnaam" not in reader.fieldnames:
            raise ValueError("The selected CSV is missing the 'Mapnaam' column.")

        for row in reader:
            if _is_cancelled(stop_event):
                _log(logger, "Process cancelled.")
                return {}

            if not row:
                continue

            name = (row.get("Mapnaam") or "").strip()
            if not name:
                continue

            if name.lower().startswith("unieke naam"):
                continue

            valid_ie_map[name.lower()] = name

    _log(logger, f"Valid IE folders: {len(valid_ie_map)}")
    return valid_ie_map


def _record_operation(operations, source_path, target_path):
    if operations is None:
        return

    operations.append(
        {
            "source": str(source_path),
            "target": str(target_path),
        }
    )


def move_item(source_path, target_path, dry_run, operations=None):
    if dry_run:
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_path), str(target_path))
    _record_operation(operations, source_path, target_path)


def move_to_extra(root_path, extra_items, dry_run, stop_event=None, logger=None, operations=None):
    extra_dir = root_path / EXTRA_DIR_NAME

    for item in extra_items:
        if _is_cancelled(stop_event):
            _log(logger, "Process cancelled.")
            return

        _log(logger, f"MOVE TO EXTRA: {item.name}")
        move_item(item, extra_dir / item.name, dry_run, operations=operations)


def move_unmatched_directories(
    root_path,
    valid_ie_map,
    dry_run,
    stop_event=None,
    logger=None,
    operations=None,
):
    extra_dir = root_path / EXTRA_DIR_NAME

    for item in root_path.iterdir():
        if _is_cancelled(stop_event):
            _log(logger, "Process cancelled.")
            return

        if not item.is_dir():
            continue
        if item.name.startswith("."):
            continue
        if item.name == EXTRA_DIR_NAME:
            continue

        if item.name.lower() not in valid_ie_map:
            _log(logger, f"MOVE DIR TO EXTRA: {item.name}")
            move_item(item, extra_dir / item.name, dry_run, operations=operations)


def remove_empty_directories(root_path, dry_run, stop_event=None, logger=None):
    for path in sorted(root_path.rglob("*"), reverse=True):
        if _is_cancelled(stop_event):
            _log(logger, "Process cancelled.")
            return

        if path.is_dir():
            try:
                if not any(path.iterdir()):
                    _log(logger, f"REMOVE EMPTY DIR: {path}")
                    if not dry_run:
                        path.rmdir()
            except Exception:
                pass


def preview_standard_mode(root_path, valid_ie_map):
    stats = {
        "supported_files": 0,
        "matching_files": 0,
        "matching_dirs": 0,
    }

    for item in root_path.iterdir():
        if item.name.startswith("."):
            continue

        if item.is_file():
            if item.suffix.lower() not in ALLOWED_EXTS:
                continue
            stats["supported_files"] += 1
            if item.stem.lower() in valid_ie_map:
                stats["matching_files"] += 1
        elif item.is_dir():
            if item.name == EXTRA_DIR_NAME:
                continue
            if item.name.lower() in valid_ie_map:
                stats["matching_dirs"] += 1

    return stats


def process_standard_mode(
    root_path,
    valid_ie_map,
    dry_run,
    stop_event=None,
    logger=None,
    operations=None,
):
    matched = []
    extra_files = []

    for item in root_path.iterdir():
        if _is_cancelled(stop_event):
            _log(logger, "Process cancelled.")
            return matched, extra_files

        if not item.is_file():
            continue
        if item.name.startswith("."):
            continue
        if item.suffix.lower() not in ALLOWED_EXTS:
            extra_files.append(item)
            continue

        ie_key = item.stem.lower()
        if ie_key not in valid_ie_map:
            extra_files.append(item)
            continue

        ie = valid_ie_map[ie_key]
        rep = item.suffix.lower().lstrip(".")
        target_dir = root_path / ie / rep
        target_path = target_dir / item.name

        _log(logger, f"MOVE: {item.name} -> {ie}/{rep}/")
        matched.append(item)
        move_item(item, target_path, dry_run, operations=operations)

    move_unmatched_directories(
        root_path,
        valid_ie_map,
        dry_run,
        stop_event,
        logger,
        operations=operations,
    )
    move_to_extra(
        root_path,
        extra_files,
        dry_run,
        stop_event,
        logger,
        operations=operations,
    )
    remove_empty_directories(root_path, dry_run, stop_event, logger)
    return matched, extra_files


def _match_artwork_ie(base_stem, valid_ie_map):
    if valid_ie_map:
        base_stem_lower = base_stem.lower()

        # Prefer the longest CSV match so values like "2814-001" win over "2814".
        for ie_key in sorted(valid_ie_map, key=len, reverse=True):
            if not base_stem_lower.startswith(ie_key):
                continue

            remainder = base_stem[len(ie_key):]
            match = ARTWORK_SUFFIX_PATTERN.match(remainder)
            if match:
                return ie_key, match.group("sequence")

    match = ARTWORK_PATTERN.match(base_stem)
    if not match:
        return None, None

    return match.group("ie").lower(), match.group("sequence")


def parse_artwork_filename(file_path, valid_ie_map=None):
    stem = file_path.stem
    variant_suffix = ""
    is_master = False

    if stem.endswith("_M"):
        is_master = True
        variant_suffix = "_M"
        base_stem = stem[:-2]
    elif stem.endswith("_B"):
        variant_suffix = "_B"
        base_stem = stem[:-2]
    else:
        base_stem = stem

    ie_key, sequence = _match_artwork_ie(base_stem, valid_ie_map)
    if not ie_key:
        return None

    return {
        "ie_key": ie_key,
        "sequence": sequence,
        "is_master": is_master,
        "variant_suffix": variant_suffix,
    }


def preview_artwork_mode(root_path, valid_ie_map):
    stats = {
        "supported_files": 0,
        "matching_files": 0,
    }

    for item in root_path.iterdir():
        if item.name.startswith(".") or not item.is_file():
            continue
        if item.suffix.lower() not in ALLOWED_EXTS:
            continue

        stats["supported_files"] += 1
        parsed = parse_artwork_filename(item, valid_ie_map=valid_ie_map)
        if parsed and parsed["ie_key"] in valid_ie_map:
            stats["matching_files"] += 1

    return stats


def validate_batch_inputs(root_path, valid_ie_map, mode):
    if not valid_ie_map:
        raise ValueError("The selected CSV does not contain any usable Mapnaam values.")

    if mode == "artwork":
        stats = preview_artwork_mode(root_path, valid_ie_map)
        if stats["supported_files"] > 0 and stats["matching_files"] == 0:
            raise ValueError("The selected CSV does not match the selected ROOT folder.")
        return

    stats = preview_standard_mode(root_path, valid_ie_map)
    if (
        stats["supported_files"] > 0
        and stats["matching_files"] == 0
        and stats["matching_dirs"] == 0
    ):
        raise ValueError("The selected CSV does not match the selected ROOT folder.")


def process_artwork_batch_mode(
    root_path,
    valid_ie_map,
    dry_run,
    stop_event=None,
    logger=None,
    operations=None,
):
    matched = []
    extra_files = []

    for item in root_path.iterdir():
        if _is_cancelled(stop_event):
            _log(logger, "Process cancelled.")
            return matched, extra_files

        if not item.is_file():
            continue
        if item.name.startswith("."):
            continue
        if item.suffix.lower() not in ALLOWED_EXTS:
            extra_files.append(item)
            continue

        parsed = parse_artwork_filename(item, valid_ie_map=valid_ie_map)
        if not parsed or parsed["ie_key"] not in valid_ie_map:
            extra_files.append(item)
            continue

        ie = valid_ie_map[parsed["ie_key"]]
        folder_name = "Masters_16bit" if parsed["is_master"] else "Bewerkt_8bit"
        target_name = item.name
        target_path = root_path / ie / folder_name / target_name

        _log(logger, f"MOVE: {item.name} -> {ie}/{folder_name}/{target_name}")
        matched.append(item)
        move_item(item, target_path, dry_run, operations=operations)

    move_unmatched_directories(
        root_path,
        valid_ie_map,
        dry_run,
        stop_event,
        logger,
        operations=operations,
    )
    move_to_extra(
        root_path,
        extra_files,
        dry_run,
        stop_event,
        logger,
        operations=operations,
    )
    remove_empty_directories(root_path, dry_run, stop_event, logger)
    return matched, extra_files


def run_batch(root_path, csv_path, dry_run, stop_event=None, mode="standard", logger=None):
    root = Path(root_path)
    csv_file = Path(csv_path)
    valid_ie_map = parse_csv(csv_file, stop_event=stop_event, logger=logger)
    validate_batch_inputs(root, valid_ie_map, mode)

    if _is_cancelled(stop_event):
        return {
            "root_path": str(root),
            "mode": mode,
            "operations": [],
            "matched_count": 0,
            "extra_count": 0,
            "cancelled": True,
        }

    modes = {
        "standard": process_standard_mode,
        "artwork": process_artwork_batch_mode,
    }
    processor = modes.get(mode, process_standard_mode)
    operations = []

    _log(logger, f"Processing mode: {mode}")
    matched, extra_files = processor(
        root,
        valid_ie_map,
        dry_run,
        stop_event=stop_event,
        logger=logger,
        operations=operations,
    )

    result = {
        "root_path": str(root),
        "mode": mode,
        "operations": operations,
        "matched_count": len(matched),
        "extra_count": len(extra_files),
        "cancelled": _is_cancelled(stop_event),
    }

    if _is_cancelled(stop_event):
        return result

    _log(logger, "==============================")
    _log(logger, f"Moved (matched): {len(matched)}")
    _log(logger, f"Moved to EXTRA: {len(extra_files)}")
    _log(logger, "Done.")
    return result


def undo_batch(root_path, operations, logger=None):
    root = Path(root_path)
    undone = 0
    skipped = 0

    for operation in reversed(operations):
        source_path = Path(operation["source"])
        target_path = Path(operation["target"])

        if not target_path.exists():
            skipped += 1
            _log(logger, f"UNDO SKIPPED: {target_path}")
            continue

        source_path.parent.mkdir(parents=True, exist_ok=True)
        _log(logger, f"UNDO: {target_path.name} -> {source_path}")
        shutil.move(str(target_path), str(source_path))
        undone += 1

    remove_empty_directories(root, False, logger=logger)
    return {
        "root_path": str(root),
        "undone_count": undone,
        "skipped_count": skipped,
    }
