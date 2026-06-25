"""Background workspace cleanup — deletes stale temp files on session start."""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def run_workspace_gc(workspace_dir: Path, temp_dir: str = "temp",
                     max_age_hours: int = 48, max_size_mb: int = 500):
    """Run garbage collection on the workspace temp directory.

    - Deletes files older than *max_age_hours*.
    - If total size exceeds *max_size_mb*, deletes oldest files first.
    - Only touches ``<workspace_dir>/<temp_dir>/``.
    - Symlinks are NOT followed.
    - Empty directories are removed after file deletion.
    """
    temp_path = (workspace_dir / temp_dir).resolve()
    if not temp_path.exists():
        return
    if not temp_path.is_dir():
        logger.warning("workspace temp dir %s is not a directory — skipping GC", temp_path)
        return

    now = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted_count = 0
    deleted_bytes = 0

    # Pass 1: delete age-expired files
    for root, dirs, files in os.walk(str(temp_path)):
        for name in files:
            fp = Path(root) / name
            if fp.is_symlink():
                continue
            try:
                st = fp.stat()
                if (now - st.st_mtime) > max_age_seconds:
                    size = st.st_size
                    fp.unlink()
                    deleted_count += 1
                    deleted_bytes += size
            except (OSError, IOError) as e:
                logger.debug("workspace GC: could not delete %s: %s", fp, e)

    # Pass 2: size-based eviction (oldest first)
    current_bytes = _dir_size(temp_path)
    if max_size_mb > 0 and current_bytes > max_size_mb * 1024 * 1024:
        all_files = []
        for root, dirs, files in os.walk(str(temp_path)):
            for name in files:
                fp = Path(root) / name
                if fp.is_symlink():
                    continue
                try:
                    st = fp.stat()
                    all_files.append((st.st_mtime, st.st_size, fp))
                except (OSError, IOError):
                    pass
        all_files.sort()
        while current_bytes > max_size_mb * 1024 * 1024 and all_files:
            mtime, size, fp = all_files.pop(0)
            try:
                fp.unlink()
                current_bytes -= size
                deleted_count += 1
                deleted_bytes += size
            except (OSError, IOError):
                pass

    # Remove empty directories (bottom-up)
    for root, dirs, files in os.walk(str(temp_path), topdown=False):
        if root == str(temp_path):
            continue
        try:
            if not os.listdir(root):
                os.rmdir(root)
        except (OSError, IOError):
            pass

    if deleted_count:
        logger.info(
            "workspace GC: deleted %d files (%d MB) from %s",
            deleted_count, deleted_bytes // (1024 * 1024), temp_path,
        )


def _dir_size(path: Path) -> int:
    """Total bytes of all regular files under *path*."""
    total = 0
    for root, dirs, files in os.walk(str(path)):
        for name in files:
            fp = Path(root) / name
            if fp.is_symlink():
                continue
            try:
                total += fp.stat().st_size
            except (OSError, IOError):
                pass
    return total
