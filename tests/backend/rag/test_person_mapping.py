import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from backend.rag.retriever_v2 import _build_token_filter

class TestPersonMapping(unittest.TestCase):
    
    def test_build_token_filter_combines_names_and_tokens_with_or(self):
        # Wenn eine Person per Token [PER_1] und als Name (Sarah) übergeben wird,
        # soll die DB mit einem ODER-Filter durchsucht werden.
        filter_dict = _build_token_filter(
            person_tokens=["[PER_1]"],
            person_names=["Sarah"],
            location_tokens=[],
            date_from=None,
            date_to=None,
            user_id="user-123",
            collection="photos"
        )
        
        self.assertIsNotNone(filter_dict, "Der Filter darf für photos nicht None sein.")
        self.assertIn("$or", filter_dict, "Es muss eine ODER-Bedingung generiert werden für Token+Name.")
        
        or_conditions = filter_dict["$or"]
        self.assertEqual(len(or_conditions), 2, "Es sollte für ein Token und einen Namen 2 ODER-Bedingungen geben.")
        
        fields = [list(cond.keys())[0] for cond in or_conditions]
        
        self.assertIn("has_per_1", fields, "Das Mapping für den Token fehlt in den DB-Feldern.")
        self.assertIn("has_sarah", fields, "Das Mapping für den Klarnamen fehlt in den DB-Feldern.")
        
    def test_build_token_filter_single_name(self):
        # Nur Name, kein Token (aus Fallback Parser)
        filter_dict = _build_token_filter(
            person_tokens=[],
            person_names=["Nora"],
            location_tokens=[],
            date_from=None,
            date_to=None,
            user_id="user-123",
            collection="photos"
        )
        self.assertIsNotNone(filter_dict)
        self.assertNotIn("$or", filter_dict, "Bei nur einem Feld sollte kein $or nötig sein.")
        self.assertEqual(filter_dict, {"has_nora": {"$eq": True}})

if __name__ == '__main__':
    unittest.main()
