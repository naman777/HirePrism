import pytest

from src.cleaning.normalize_branches import BRANCH_MAP, build_bridge, normalize_branch


# ── All 23 raw codes should resolve ──────────────────────────────────────────


@pytest.mark.parametrize("raw_code", list(BRANCH_MAP.keys()))
def test_all_known_codes_resolve(raw_code):
    r = normalize_branch(raw_code)
    assert r["branch_standardized"] != ""
    assert r["branch_group"] != ""


# ── Specific group assertions ─────────────────────────────────────────────────


def test_copc_is_cs():
    assert normalize_branch("COPC")["branch_group"] == "CS"


def test_coe_is_cs():
    assert normalize_branch("COE")["branch_group"] == "CS"


def test_cobs_is_cs():
    assert normalize_branch("COBS")["branch_group"] == "CS"


def test_ece_is_ece_group():
    assert normalize_branch("ECE")["branch_group"] == "ECE"


def test_enc_is_ece_group():
    assert normalize_branch("ENC")["branch_group"] == "ECE"


def test_eec_is_ece_group():
    assert normalize_branch("EEC")["branch_group"] == "ECE"


def test_eic_is_ece_group():
    assert normalize_branch("EIC")["branch_group"] == "ECE"


def test_ele_is_ece_group():
    assert normalize_branch("ELE")["branch_group"] == "ECE"


def test_mec_is_mech():
    assert normalize_branch("MEC")["branch_group"] == "MECH"


def test_me_is_mech():
    assert normalize_branch("ME")["branch_group"] == "MECH"


def test_cie_is_civil():
    assert normalize_branch("CIE")["branch_group"] == "CIVIL"


def test_che_is_chem():
    assert normalize_branch("CHE")["branch_group"] == "CHEM"


def test_mtech_is_pg():
    assert normalize_branch("M.E./MTech")["branch_group"] == "PG"


def test_mca_is_pg():
    assert normalize_branch("MCA")["branch_group"] == "PG"


def test_all_branches_is_all():
    r = normalize_branch("B.E. All Branches")
    assert r["branch_standardized"] == "ALL"
    assert r["branch_group"] == "ALL"


def test_not_applicable_is_na():
    assert normalize_branch("Not Applicable")["branch_group"] == "NA"


def test_not_known_is_unknown():
    assert normalize_branch("Not Known")["branch_group"] == "UNKNOWN"


def test_unrecognized_code_is_unknown():
    r = normalize_branch("XYZ_FAKE")
    assert r["branch_standardized"] == "UNKNOWN"
    assert r["branch_group"] == "UNKNOWN"


# ── Bridge table ──────────────────────────────────────────────────────────────


def test_bridge_one_row_per_branch():
    import pandas as pd

    df = pd.DataFrame(
        [
            {"offer_id": "aaa", "branches_allowed_raw": ["ECE", "MEE"]},
            {"offer_id": "bbb", "branches_allowed_raw": ["COE"]},
        ]
    )
    bridge = build_bridge(df)
    assert len(bridge) == 3
    assert set(bridge["offer_id"]) == {"aaa", "bbb"}


def test_bridge_empty_branches_produces_unknown_row():
    import pandas as pd

    df = pd.DataFrame([{"offer_id": "x", "branches_allowed_raw": []}])
    bridge = build_bridge(df)
    assert len(bridge) == 1
    assert bridge.iloc[0]["branch_standardized"] == "UNKNOWN"


def test_bridge_columns():
    import pandas as pd

    df = pd.DataFrame([{"offer_id": "x", "branches_allowed_raw": ["ECE"]}])
    bridge = build_bridge(df)
    assert set(bridge.columns) == {"offer_id", "branch_raw", "branch_standardized", "branch_group"}
