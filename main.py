async def send_to_sillytavern(user_message: str):
    # Try the most common ways SillyTavern accepts external messages
    payloads = [
        # Method 1: Simple chat endpoint (some forks / extensions use this)
        {
            "input": user_message,
            "character": CHARACTER_NAME,
            "user": USER_NAME
        },
        # Method 2: More standard prompt-style
        {
            "prompt": user_message,
            "character": CHARACTER_NAME,
            "user": USER_NAME,
            "max_new_tokens": 300,
            "temperature": 0.85
        }
    ]
    
    async with httpx.AsyncClient(timeout=90.0) as client:
        for payload in payloads:
            try:
                resp = await client.post(
                    urljoin(ST_URL, "/api/chat"), 
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Try different possible response keys
                    reply = (data.get("response") or 
                            data.get("result") or 
                            data.get("text") or 
                            str(data))
                    return reply if len(reply) > 5 else "……ちょっと待ってね💦"
            except:
                continue  # try next payload format
                
        # If all failed, fallback message
        return "ごめん、今ちょっと接続が不安定みたい……もう一度言ってみて？"
