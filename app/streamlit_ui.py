"""
streamlit_ui.py — Local Evaluator Dashboard & Chat Interface

This UI demonstrates the API endpoint. It allows you to chat with the agent
and inspect the raw stateless JSON payloads being sent to and received from the API.
"""

import streamlit as st
import requests
import json
import os
import time

def stream_data(text: str):
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.03)

API_URL = "http://localhost:8000/chat"

st.set_page_config(page_title="Assessment Recommendation Tool — Local Evaluator", layout="wide")

st.title("Assessment Recommendation Tool 🔍")
st.markdown("This dashboard interacts with your local FastAPI server. Ensure `uvicorn app.main:app` is running.")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for State Inspection & Logs
with st.sidebar:
    st.header("Admin Panel (Server Logs)")
    log_path = "logs/agent_errors.log"
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                logs = f.read()
            # Show only the last 2000 characters to keep UI snappy
            st.text_area("Live Backend Logs", value=logs[-2000:] if len(logs) > 2000 else logs, height=200, disabled=True)
            if st.button("Clear Logs"):
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("")
                st.rerun()
        except Exception as e:
            st.error(f"Could not read logs: {e}")
    else:
        st.info("No server logs generated yet.")
        
    st.divider()
    
    st.header("State Inspector (Stateless Proof)")
    st.markdown("Because the API is stateless, **every single request** must contain the entire conversation history. Below is the exact payload that will be sent on the next message:")
    
    payload = {"messages": st.session_state.messages}
    st.json(payload, expanded=False)
    
    st.header("Last API Response")
    if "last_response" in st.session_state:
        st.json(st.session_state.last_response, expanded=True)
    else:
        st.info("No requests made yet.")
        
    if st.button("Clear Conversation"):
        st.session_state.messages = []
        if "last_response" in st.session_state:
            del st.session_state["last_response"]
        st.rerun()

# Main Chat Interface
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("E.g. We need an assessment for a Senior Java Developer"):
    # 1. Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Call the FastAPI endpoint
    with st.chat_message("assistant"):
        with st.spinner("Agent is thinking..."):
            try:
                # Send the entire stateless payload
                res = requests.post(API_URL, json={"messages": st.session_state.messages})
                
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.last_response = data
                    
                    reply = data.get("reply", "")
                    recs = data.get("recommendations", [])
                    eoc = data.get("end_of_conversation", False)
                    
                    st.write_stream(stream_data(reply))
                    
                    if recs:
                        st.markdown("### Recommendations:")
                        for idx, r in enumerate(recs, 1):
                            with st.expander(f"{idx}. {r.get('name')}"):
                                st.markdown(f"**URL:** {r.get('url')}")
                                st.markdown(f"**Test Type (Keys):** {r.get('test_type')}")
                                if r.get('job_levels'):
                                    st.markdown(f"**Levels:** {', '.join(r.get('job_levels'))}")
                                if r.get('languages'):
                                    st.markdown(f"**Languages:** {len(r.get('languages'))} available")
                                st.markdown(f"**Reason:** {r.get('reason')}")
                    
                    if eoc:
                        st.success("✅ The agent indicated the conversation has reached its end (end_of_conversation: true).")
                    
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                else:
                    st.error(f"API Error {res.status_code}: {res.text}")
                    
            except requests.exceptions.ConnectionError:
                st.error("Could not connect to the API. Is `uvicorn app.main:app` running?")