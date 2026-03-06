import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from backend.rag.retriever_v2 import _get_system_prompt

class TestEmotionToolPrompt(unittest.TestCase):
    
    def test_agent_system_prompt_enforces_search_messages_for_emotions(self):
        prompt = _get_system_prompt()
        
        # Der Agent muss zwingend angewiesen werden, search_messages für Gefühle zu nutzen
        self.assertIn("search_messages", prompt, 
                      "Der System-Prompt erwähnt das Tool `search_messages` nicht.")
        self.assertIn("Gefühl", prompt,
                      "Der System-Prompt enthält keine explizite Regel für Gefühle/Emotionen.")
        self.assertIn("MUSST du zwingend das Tool", prompt,
                      "Die Regel für Emotionen ist nicht stark genug formuliert (muss 'MUSST du zwingend' enthalten).")

if __name__ == '__main__':
    unittest.main()
