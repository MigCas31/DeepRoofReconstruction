import subprocess
from pathlib import Path


def test_phase_h_node_unit_tests_pass():
    result = subprocess.run(
        ["node", "--test", *sorted(str(path) for path in Path("tests/reconcile_tiers/web/js").glob("*.mjs"))],
        cwd=Path(__file__).parents[3],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_tier_web_does_not_reintroduce_renderer_fixups():
    web_dir = Path("reconcile_tiers/web")
    banned = [
        "MATERIALS.ceiling",
        "walls_merged",
        "flattenToMeanY",
        "orientHorizontalLidUp",
        "polygonPlaneBasis",
        "computeBuildingCenter",
    ]

    contents = "\n".join(path.read_text() for path in web_dir.glob("*.js"))

    for token in banned:
        assert token not in contents


def test_static_tier_viewer_runtime_is_decoupled_from_legacy_reconcile_paths():
    web_dir = Path("reconcile_tiers/web")
    web_contents = "\n".join(path.read_text() for path in web_dir.glob("*.*"))
    web_banned = [
        "/tier-index",
        "/building-merged",
        "viewer_server",
        "viewer-main",
        "viewer-modules",
        "ontology",
        "reconcile_v2",
        "reconcile_v3",
    ]
    for token in web_banned:
        assert token not in web_contents

    runtime_files = [
        path
        for path in Path("reconcile_tiers").rglob("*.py")
        if "archive" not in path.parts
        and "scripts" not in path.parts
        and "__pycache__" not in path.parts
    ]
    py_banned = [
        "from reconcile ",
        "from reconcile.",
        "import reconcile ",
        "import reconcile.",
        "reconcile_v2",
        "reconcile_v3",
    ]
    offenders = [
        (str(path), token)
        for path in runtime_files
        for token in py_banned
        if token in path.read_text()
    ]

    assert offenders == []


def test_tier_viewer_exposes_clickable_locator_selection():
    html = Path("reconcile_tiers/web/viewer-tiers.html").read_text()
    main_js = Path("reconcile_tiers/web/viewer-tiers-main.js").read_text()

    assert 'src="./viewer-tiers-main.js"' in html
    assert 'selectedLocator: null' in main_js
    assert 'canvas.addEventListener("click"' in main_js
    assert 'canvas.addEventListener("contextmenu"' in main_js
    assert 'new THREE.BoxHelper' in main_js
    assert 'navigator.clipboard' in main_js


def test_tier_preview_renders_only_front_faces_for_opaque_surfaces():
    preview_js = Path("reconcile_tiers/web/tier-preview.js").read_text()

    assert 'side: def.name === "window" ? THREE.DoubleSide : THREE.FrontSide' in preview_js
