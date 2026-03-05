import os
import sys

# Pfad zum Backend hinzufügen
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.rag.retriever_v2 import answer_v2

# Wir loggen alles um das Agententreiben zu sehen
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# User ID from the context (e.g., from DB init)
USER_ID = "00000000-0000-0000-0000-000000000001"

def test_basic():
    print("\n--- TEST: Retro-Kompatibilität (Bilder in München) ---")
    res = answer_v2(
        masked_query="Bilder in [LOC_1]",
        user_id=USER_ID,
        location_tokens=["[LOC_1]"],
        location_names=["München"]
    )
    print("\nANTWORT:\n", res["answer"])

def test_multihop():
    print("\n--- TEST: Multi-Hop (Wie ging es [PER_4] als ich in [LOC_1] war?) ---")
    res = answer_v2(
        masked_query="Wie ging es [PER_4], als ich in [LOC_1] war?",
        user_id=USER_ID,
        person_tokens=["[PER_4]"],
        location_tokens=["[LOC_1]"],
        location_names=["München"]
    )
    print("\nANTWORT:\n", res["answer"])

if __name__ == "__main__":
    test_basic()
    test_multihop()
