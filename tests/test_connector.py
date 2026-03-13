import pytest
import asyncio
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.llm.connector import chat_stream

class MockPart:
    def __init__(self, text=None, function_call=None):
        if text is not None:
            self.text = text
        if function_call is not None:
            self.function_call = function_call

class MockFunctionCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args

class MockResponse:
    def __init__(self, parts, text=""):
        self.parts = parts
        self.text = text

# Ein einfaches Mock-Tool für unseren Test
def dummy_tool(query):
    return "Tool Ergebnis"

@pytest.mark.asyncio
async def test_chat_stream_extracts_transparent_reasoning():
    # Wir simulieren eine Gemini Response, die zuerst "Denkt" (text-Part) 
    # und dann ein Tool aufruft (function_call-Part).
    
    mock_thought = "Ich muss zuerst dummy_tool verwenden, um Daten zu finden."
    mock_fc = MockFunctionCall(name="dummy_tool", args={"query": "test"})
    
    # Der erste Response liefert das Tool, der zweite den finalen Text
    mock_responses = [
        MockResponse(parts=[MockPart(text=mock_thought), MockPart(function_call=mock_fc)]),
        MockResponse(parts=[], text="Hier ist die finale Antwort.")
    ]
    
    response_iterator = iter(mock_responses)
    
    mock_chat_session = MagicMock()
    def side_effect(*args, **kwargs):
        return next(response_iterator)
    mock_chat_session.send_message.side_effect = side_effect

    mock_model = MagicMock()
    mock_model.start_chat.return_value = mock_chat_session

    with patch('google.generativeai.GenerativeModel', return_value=mock_model), \
         patch('google.generativeai.configure'), \
         patch('backend.llm.connector.get_cfg', return_value={'llm': {'provider': 'gemini', 'model': 'test-model'}}):
        
        # Aufruf des asynchronen Generators
        stream = chat_stream(
            messages=[{"role": "user", "content": "Hallo"}],
            tools=[dummy_tool]
        )
        
        events = []
        async for event in stream:
            events.append(event)
            
        # Wir erwarten 3 Events: 
        # 1. Den extrahierten Plan-Text
        # 2. Den Platzhalter "Formuliere Antwort..."
        # 3. Den finalen Text
        
        assert len(events) == 3
        
        assert events[0]["type"] == "plan"
        assert events[0]["content"] == mock_thought, "Der Denk-Prozess wurde nicht korrekt an das Frontend weitergeleitet!"
        
        assert events[1]["type"] == "plan"
        assert events[1]["content"] == "Formuliere Antwort..."
        
        assert events[2]["type"] == "text"
        assert "finale Antwort" in events[2]["content"]
