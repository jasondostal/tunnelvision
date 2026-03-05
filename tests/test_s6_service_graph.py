"""Validate s6-overlay service dependency graph.

Catches dangling references in dependencies.d/ and contents.d/ — the class
of bug introduced when renaming services (e.g. init-wireguard → init-vpn)
without updating all referencing files.

No s6 binaries required. Pure filesystem validation.
"""

from pathlib import Path

S6_RC_D = Path(__file__).parent.parent / "rootfs/etc/s6-overlay/s6-rc.d"

# s6-overlay built-in virtual services — not directories in our tree
S6_BUILTINS = {"base"}

# Bundle directories (contents.d/ instead of type file)
S6_BUNDLES = {"user"}


def _service_names() -> set[str]:
    """All defined service names (directories in s6-rc.d) plus builtins."""
    return {d.name for d in S6_RC_D.iterdir() if d.is_dir()} | S6_BUILTINS


def _all_references() -> list[tuple[str, str]]:
    """All (file_path, referenced_service) pairs across dependencies.d and contents.d."""
    refs = []
    for ref_file in S6_RC_D.rglob("dependencies.d/*"):
        if ref_file.is_file():
            refs.append((str(ref_file), ref_file.name))
    for ref_file in S6_RC_D.rglob("contents.d/*"):
        if ref_file.is_file():
            refs.append((str(ref_file), ref_file.name))
    return refs


class TestS6ServiceGraph:
    def test_all_services_have_type_file(self):
        """Every service directory (except bundles) must have a 'type' file."""
        missing = []
        for svc in S6_RC_D.iterdir():
            if svc.is_dir() and svc.name not in S6_BUNDLES and not (svc / "type").exists():
                missing.append(svc.name)
        assert not missing, f"Services missing 'type' file: {missing}"

    def test_no_dangling_dependency_references(self):
        """Every name in dependencies.d/ must resolve to a real service directory."""
        services = _service_names()
        dangling = [
            f"{path} → '{ref}' (not found)"
            for path, ref in _all_references()
            if ref not in services
        ]
        assert not dangling, (
            "Dangling s6 service references found:\n" + "\n".join(dangling)
        )

    def test_user_bundle_contains_all_init_services(self):
        """user/contents.d should include every init-* and svc-* service."""
        user_contents = {
            f.name for f in (S6_RC_D / "user" / "contents.d").iterdir()
            if f.is_file()
        }
        all_services = _service_names()
        runnable = {s for s in all_services if s.startswith(("init-", "svc-"))}
        missing = runnable - user_contents - {"user"}
        assert not missing, (
            f"Services not registered in user bundle: {missing}"
        )

    def test_oneshot_services_have_up_script(self):
        """Oneshot services must have an 'up' file."""
        missing_up = []
        for svc in S6_RC_D.iterdir():
            if not svc.is_dir():
                continue
            type_file = svc / "type"
            if type_file.exists() and type_file.read_text().strip() == "oneshot":
                if not (svc / "up").exists():
                    missing_up.append(svc.name)
        assert not missing_up, f"Oneshot services missing 'up' script: {missing_up}"
