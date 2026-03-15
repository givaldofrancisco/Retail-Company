import sys
from pathlib import Path

try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.safety.pii_masker import PIIMasker
except ModuleNotFoundError:
    PIIMasker = None


def test_sanitize_dataframe_removes_sensitive_columns_and_masks_text():
    if pd is None or PIIMasker is None:
        raise AssertionError("pandas is required for this test")
    masker = PIIMasker()
    df = pd.DataFrame(
        [
            {
                "customer_id": 1,
                "email": "alice@example.com",
                "phone_number": "+1 555-111-2222",
                "note": "Reach me at bob@example.org",
            }
        ]
    )

    result = masker.sanitize_dataframe(df)
    print("sanitize_dataframe -> removed_columns:", result.removed_columns)
    print("sanitize_dataframe -> remaining", list(result.dataframe.columns))
    print("sanitize_dataframe -> note:", result.dataframe.iloc[0]["note"])
    assert "email" in result.removed_columns
    assert "phone_number" in result.removed_columns
    assert "email" not in result.dataframe.columns
    assert "phone_number" not in result.dataframe.columns
    assert "[REDACTED_EMAIL]" in result.dataframe.iloc[0]["note"]


def test_mask_text_masks_phone_and_email():
    if PIIMasker is None:
        raise AssertionError("pandas is required for this test")
    masker = PIIMasker()
    text = "Contact me at jane@company.com or +1 (202) 555-0199"
    masked = masker.mask_text(text)
    print("mask_text -> input:", text)
    print("mask_text -> output:", masked)
    assert "jane@company.com" not in masked
    assert "555" not in masked
    assert "[REDACTED_EMAIL]" in masked
    assert "[REDACTED_PHONE]" in masked


if __name__ == "__main__":
    if pd is None or PIIMasker is None:
        print("ERRO: pandas não está instalado neste Python.")
        print("Use a venv do projeto:")
        print('  cd "/Users/ctw01670/Documents/CTW/Project/My Projects/Retail Company"')
        print("  source .venv/bin/activate")
        print("  python3 tests/test_pii_masking.py")
        raise SystemExit(1)

    test_sanitize_dataframe_removes_sensitive_columns_and_masks_text()
    print("[PASSOU] sanitize_dataframe_removes_sensitive_columns_and_masks_text")
    test_mask_text_masks_phone_and_email()
    print("[PASSOU] mask_text_masks_phone_and_email")
    print("Resumo: 2/2 checks aprovados")
