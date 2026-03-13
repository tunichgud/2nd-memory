import unittest
from unittest.mock import patch
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.rag.retriever_v2 import _get_system_prompt
from backend.rag.query_parser import _get_parse_system_prompt

class TestLLMDateAwareness(unittest.TestCase):
    
    @patch('backend.rag.retriever_v2.datetime')
    def test_agent_system_prompt_knows_current_date(self, mock_datetime):
        # Mocke das aktuelle Datum auf ein festes Datum in der Zukunft
        mock_date = datetime(2035, 10, 21)
        mock_datetime.now.return_value = mock_date
        
        prompt = _get_system_prompt()
        
        # Der Agent muss das exakte tagesaktuelle Datum kennen
        expected_date_str = "21.10.2035"
        self.assertIn(expected_date_str, prompt, 
                      f"Der Agent-Prompt enthält nicht das korrekte aktuelle Datum ({expected_date_str}).")
        self.assertIn("HEUTIGES DATUM:", prompt,
                      "Der Agent-Prompt hat den Abschnitt 'HEUTIGES DATUM:' verloren.")

    @patch('backend.rag.query_parser.datetime')
    def test_query_parser_prompt_knows_current_year(self, mock_datetime):
        # Mocke das aktuelle Jahr
        mock_date = datetime(2042, 5, 1)
        mock_datetime.now.return_value = mock_date
        
        prompt = _get_parse_system_prompt()
        
        # Der Query Parser muss das aktuelle Jahr kennen, um "letztes Jahr" korrekt zu parsen
        expected_year_str = "2042"
        self.assertIn(expected_year_str, prompt, 
                      f"Der Query-Parser-Prompt enthält nicht das korrekte aktuelle Jahr ({expected_year_str}).")

if __name__ == '__main__':
    unittest.main()
