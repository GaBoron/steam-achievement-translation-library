"""Clean disposable workflow data and recycle obsolete local repository files."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def temporary_directory():
    """Clean owned temporary work without depending on a desktop Trash backend."""
    temporary = tempfile.TemporaryDirectory(prefix="translation-library-", ignore_cleanup_errors=True)
    path = Path(temporary.name)
    try:
        yield path
    finally:
        try:
            temporary.cleanup()
        except OSError as exc:
            warnings.warn(f"Could not clean temporary directory {path}: {exc}", RuntimeWarning)


def recycle_path(path: Path, *, boundary: Path) -> None:
    """Remove exact workflow files in Actions; require Trash for local repository files."""
    target = path.resolve(strict=True)
    root = boundary.resolve(strict=True)
    if target == root or not target.is_relative_to(root) or path.is_symlink():
        raise ValueError(f"Refusing to recycle target outside its variant boundary: {path}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # The Actions checkout is disposable and reviewed files remain in Git.
        # Never recursively remove repository directories or follow file symlinks.
        if not target.is_file():
            raise ValueError(f"Workflow cleanup requires a regular file: {path}")
        target.unlink()
        return
    if os.name == "nt":
        try:
            import pythoncom
            from win32com.shell import shell
        except ImportError as exc:
            raise RuntimeError(f"Recycle Bin support requires pywin32; file left in place: {target}") from exc
        pythoncom.CoInitialize()
        try:
            operation = pythoncom.CoCreateInstance(
                shell.CLSID_FileOperation, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IFileOperation,
            )
            # IFileOperation: RECYCLEONDELETE + ADDUNDORECORD + EARLYFAILURE,
            # with silent progress and error UI. Never use SHFileOperation's
            # best-effort ALLOWUNDO, which can fall back to permanent deletion.
            operation.SetOperationFlags(0x00080000 | 0x20000000 | 0x00100000 | 0x4 | 0x10 | 0x400)
            item = shell.SHCreateItemFromParsingName(str(target), None, shell.IID_IShellItem)
            operation.DeleteItem(item, None)
            result = operation.PerformOperations()
            if result or operation.GetAnyOperationsAborted() or target.exists():
                raise RuntimeError(f"Could not move to Recycle Bin: {target} (code {result})")
        except Exception as exc:
            raise RuntimeError(f"Recycle Bin operation failed for {target}: {exc}") from exc
        finally:
            pythoncom.CoUninitialize()
        return
    gio = shutil.which("gio")
    if gio:
        try:
            subprocess.run([gio, "trash", "--", str(target)], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(f"Could not move to Trash; file left in place: {target}: {detail}") from exc
        if not target.exists():
            return
    raise RuntimeError(f"Trash unavailable; obsolete file left in place: {target}")
