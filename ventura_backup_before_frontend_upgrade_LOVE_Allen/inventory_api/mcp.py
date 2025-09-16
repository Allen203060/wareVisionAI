import os
import json
import requests

def get_llm_reasoning(prompt: str) -> dict:
    """
    Sends a prompt to a local LLM (via Ollama) and gets a reasoned action.
    This is now a generic function that takes any prompt.
    """

    ollama_api_url = "http://localhost:11434/api/generate"
    # Sends a prompt to a local LLM (via LM Studio) and gets a reasoned action.
    # LM Studio's local se
    # rver runs on port 1234 and mimics the OpenAI API structure
    # default_url = "http://26.113.213.80:1234/v1/chat/completions"
    # lm_studio_api_url = os.environ.get(

    #     'LM_STUDIO_URL', default_url
    # )

    # if "WINDOWS_HOST_IP" in lm_studio_api_url:
    #      return {"error": "LM Studio URL is not configured. Please edit inventory_api/mcp.py and set your Windows host IP."}
    
    # headers = {"Content-Type": "application/json"}

    # The payload needs to be in the OpenAI chat completions format

    payload = {
        "model": "mistral",
        "prompt": prompt,
        "stream": False,
        "format": "json"
        # The model name is often ignored by LM Studio; it uses the model loaded in the UI.
        # However, it's good practice to include it.
        # "model": "openai/gptoss-oss-20b", 
        # "messages": [
        #     {"role": "system", "content": "You are a helpful database assistant that only responds with valid JSON."},
        #     {"role": "user", "content": prompt}
        # ],
        # "temperature": 0.7,
        # "stream": False # We want a single response
    }
    

    
    try:
        response = requests.post(ollama_api_url, json=payload, timeout=180)
        # **FIX:** Check for non-200 status codes and print the error from Ollama.
        if response.status_code != 200:
            print(f"Ollama returned an error: {response.status_code}")
            print(f"Response body: {response.text}")
            return {"error": f"Ollama returned a non-200 status code: {response.text}"}
            
        response.raise_for_status()
        response_data = response.json()
        
        reasoned_action_string = response_data.get("response", "{}")
        reasoned_action_json = json.loads(reasoned_action_string)
        
        return reasoned_action_json

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with local LLM: {e}")
        return {"error": "Could not connect to the local language model. Is Ollama running?"}
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"Error parsing JSON from LLM response: {e}")
        response_text = response.text if 'response' in locals() else 'No response text'
        print(f"Raw response was: {response_text}")
        return {"error": "Invalid or unexpected JSON response from the model."}


