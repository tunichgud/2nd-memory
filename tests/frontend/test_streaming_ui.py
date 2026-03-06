import os
import sys
import threading
import time
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import urllib.request

# Ensure we can find the modules if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# --- Mock Server Setup ---
app = FastAPI()

# Mount the static frontend
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend'))
app.mount("/static", StaticFiles(directory=frontend_dir, html=True), name="static")

from fastapi import FastAPI, Request

@app.post("/api/v1/query_stream")
async def mock_query_stream(request: Request):
    # Simulate the SSE stream yielding a thought then a final answer
    async def event_generator():
        import asyncio
        await asyncio.sleep(0.5)
        # Yield the thought process
        yield '{"type": "plan", "content": "Das ist ein künstlicher Gedanke vom Agenten."}\n\n'
        await asyncio.sleep(0.5)
        # Yield the finish signal
        yield '{"type": "plan", "content": "Formuliere Antwort..."}\n\n'
        yield '{"type": "text", "content": "Das ist die finale Antwort des Agenten."}\n\n'
        
    return StreamingResponse(event_generator(), media_type="text/event-stream")

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")

@pytest.fixture(scope="module")
def mock_server():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    max_retries = 10
    for _ in range(max_retries):
        try:
            urllib.request.urlopen("http://127.0.0.1:8001/static/index.html")
            break
        except Exception:
            time.sleep(0.5)
    else:
        pytest.fail("Mock server did not start in time.")
        
    yield
    # No clean teardown needed since daemon=True will kill it when pytest exits

@pytest.fixture(scope="module")
def browser():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    yield driver
    driver.quit()

# --- The Actual Selenium Test ---

def test_streaming_ui_appends_thoughts(mock_server, browser):
    # Lade das Mock-Frontend
    browser.get("http://127.0.0.1:8001/static/index.html")
    
    wait = WebDriverWait(browser, 10)
    
    # Mocke die globalen Variablen für _useV2() im Frontend und blende Overlays aus
    browser.execute_script("""
        window._nerReady = true;
        window.NER = { maskText: async (t) => ({masked: t, entities: []}) };
        window.TokenStore = { lookupToken: async () => '', unmaskText: async (t) => t };
        window._userId = 'test_user';
        const overlay = document.getElementById('ner-overlay');
        if(overlay) overlay.style.display = 'none';
        const consent = document.getElementById('consent-screen');
        if(consent) consent.style.display = 'none';
    """)
    
    # Warte bis Inputfeld da ist (ID ist chat-input)
    chat_input = wait.until(EC.presence_of_element_located((By.ID, "chat-input")))
    chat_input.send_keys("Test Anfrage")
    
    # Klicke auf den Button "Fragen"
    submit_btn = browser.find_element(By.XPATH, "//button[contains(text(), 'Fragen')]")
    submit_btn.click()
    
    import time
    time.sleep(3)
    
    print("\n\n--- BROWSER LOGS ---")
    for entry in browser.get_log('browser'):
        print(entry)
    print("--------------------\n\n")
    
    # Jetzt sollte ein Plan-Bubble im DOM auftauchen
    thought_element = browser.find_elements(By.CSS_SELECTOR, ".plan-text")
    assert len(thought_element) > 0 and "künstlicher Gedanke" in thought_element[0].text, "Agent-Gedanke wurde nicht gerendert!"
    
    # Prüfe ob finale Text-Antwort da ist
    final_text = browser.find_element(By.XPATH, "//*[contains(text(), 'Das ist die finale Antwort')]")
    assert final_text is not None, "Finale Chat-Antwort nicht gerendert!"
