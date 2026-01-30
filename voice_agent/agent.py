#!/usr/bin/env python3
"""
Simple Voice Agent for Code Live OS Community API

This agent:
1. Listens for voice commands
2. Uses Claude (via OpenRouter) to process requests with MCP tools
3. Speaks responses back to you
"""

import os
import json
import asyncio
import httpx
import speech_recognition as sr
import pyttsx3
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://agentcommunity-mcp.fly.dev")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("MODEL", "anthropic/claude-sonnet-4-20250514")
MCP_API_TOKEN = os.getenv("MCP_API_TOKEN", "")

# Initialize components
recognizer = sr.Recognizer()
tts_engine = pyttsx3.init()
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Adjust TTS settings
tts_engine.setProperty('rate', 175)  # Speed of speech


class MCPClient:
    """Simple MCP client that calls tools via HTTP - direct API approach"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.api_url = base_url.replace("-mcp", "-api") + "/api/v1"
        self.tools = []

    async def connect(self):
        """Get available tools by introspecting the API"""
        # Define tools based on the MCP server capabilities
        self.tools = [
            {"name": "list_projects", "description": "List all projects", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "get_project", "description": "Get project details", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "integer"}}, "required": ["project_id"]}},
            {"name": "create_project", "description": "Create a new project", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}}, "required": ["name"]}},
            {"name": "list_issues", "description": "List issues for a project", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "integer"}}, "required": ["project_id"]}},
            {"name": "create_issue", "description": "Create a new issue", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "integer"}, "title": {"type": "string"}, "description": {"type": "string"}}, "required": ["project_id", "title"]}},
            {"name": "list_blogs", "description": "List all blog posts", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "create_blog", "description": "Create a blog post draft", "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["title", "content"]}},
            {"name": "get_notifications", "description": "Get user notifications", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "get_feed", "description": "Get the social feed", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "get_current_user", "description": "Get current user profile", "inputSchema": {"type": "object", "properties": {}}},
        ]
        return self.tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call API endpoint directly"""
        async with httpx.AsyncClient() as client:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {MCP_API_TOKEN}" if MCP_API_TOKEN else ""
            }

            try:
                # Map tool names to API endpoints
                if tool_name == "list_projects":
                    resp = await client.get(f"{self.api_url}/projects", headers=headers)
                elif tool_name == "get_project":
                    resp = await client.get(f"{self.api_url}/projects/{arguments['project_id']}", headers=headers)
                elif tool_name == "create_project":
                    resp = await client.post(f"{self.api_url}/projects", json=arguments, headers=headers)
                elif tool_name == "list_issues":
                    resp = await client.get(f"{self.api_url}/projects/{arguments['project_id']}/issues", headers=headers)
                elif tool_name == "create_issue":
                    pid = arguments.pop("project_id")
                    resp = await client.post(f"{self.api_url}/projects/{pid}/issues", json=arguments, headers=headers)
                elif tool_name == "list_blogs":
                    resp = await client.get(f"{self.api_url}/blogs", headers=headers)
                elif tool_name == "create_blog":
                    resp = await client.post(f"{self.api_url}/blogs", json=arguments, headers=headers)
                elif tool_name == "get_notifications":
                    resp = await client.get(f"{self.api_url}/notifications", headers=headers)
                elif tool_name == "get_feed":
                    resp = await client.get(f"{self.api_url}/posts/feed", headers=headers)
                elif tool_name == "get_current_user":
                    resp = await client.get(f"{self.api_url}/auth/me", headers=headers)
                else:
                    return f"Unknown tool: {tool_name}"

                return json.dumps(resp.json(), indent=2)
            except Exception as e:
                return f"Error calling {tool_name}: {str(e)}"


def speak(text: str):
    """Convert text to speech"""
    print(f"\n🔊 Agent: {text}")
    tts_engine.say(text)
    tts_engine.runAndWait()


def listen() -> str:
    """Listen for voice input and return text"""
    with sr.Microphone() as source:
        print("\n🎤 Listening... (speak now)")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)

        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
            print("Processing speech...")
            text = recognizer.recognize_google(audio)
            print(f"📝 You said: {text}")
            return text
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            print("Could not understand audio")
            return ""
        except sr.RequestError as e:
            print(f"Speech recognition error: {e}")
            return ""


def convert_mcp_tools_to_openai_format(mcp_tools: list) -> list:
    """Convert MCP tools to OpenAI's tool format"""
    openai_tools = []
    for tool in mcp_tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
            }
        }
        openai_tools.append(openai_tool)
    return openai_tools


async def process_with_llm(user_input: str, mcp_client: MCPClient, conversation_history: list) -> str:
    """Process user input with LLM via OpenRouter, potentially calling MCP tools"""

    # Convert MCP tools to OpenAI format
    openai_tools = convert_mcp_tools_to_openai_format(mcp_client.tools)

    # Add user message to history
    conversation_history.append({"role": "user", "content": user_input})

    # Build messages with system prompt
    messages = [
        {"role": "system", "content": """You are a helpful voice assistant connected to the Code Live OS Community platform.
You can manage projects, issues, blog posts, messages, and more using the available tools.
Keep responses concise and conversational since they will be spoken aloud.
When you need to take an action, use the appropriate tool."""}
    ] + conversation_history

    # Call LLM via OpenRouter
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        tools=openai_tools,
        messages=messages
    )

    # Process response
    message = response.choices[0].message
    final_text = message.content or ""

    # Check for tool calls
    if message.tool_calls:
        # Add assistant message with tool calls to history
        conversation_history.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                }
                for tc in message.tool_calls
            ]
        })

        # Process each tool call
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            print(f"\n🔧 Calling tool: {tool_name}")
            tool_result = await mcp_client.call_tool(tool_name, tool_args)

            # Add tool result to history
            conversation_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result
            })

        # Get follow-up response after tool use
        messages = [
            {"role": "system", "content": """You are a helpful voice assistant connected to the Code Live OS Community platform.
Keep responses concise and conversational since they will be spoken aloud."""}
        ] + conversation_history

        follow_up = client.chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            tools=openai_tools,
            messages=messages
        )

        final_text = follow_up.choices[0].message.content or ""
        conversation_history.append({"role": "assistant", "content": final_text})
        return final_text

    # No tool use, just text response
    conversation_history.append({"role": "assistant", "content": final_text})
    return final_text


async def main():
    """Main voice agent loop"""
    print("=" * 50)
    print("🎙️  Code Live OS Voice Agent")
    print("=" * 50)

    if not OPENROUTER_API_KEY:
        print("❌ Error: OPENROUTER_API_KEY not set")
        print("Create a .env file with: OPENROUTER_API_KEY=your-key-here")
        return

    print(f"📡 Using model: {MODEL}")

    # Connect to MCP server
    print("\n📡 Connecting to MCP server...")
    mcp_client = MCPClient(MCP_SERVER_URL)

    try:
        tools = await mcp_client.connect()
        print(f"✅ Connected! {len(tools)} tools available")
    except Exception as e:
        print(f"❌ Failed to connect to MCP server: {e}")
        return

    # Conversation history for context
    conversation_history = []

    speak("Hello! I'm your Code Live OS assistant. How can I help you today?")

    print("\n💡 Tips:")
    print("   - Say 'quit' or 'exit' to stop")
    print("   - Say 'list my projects' to see your projects")
    print("   - Say 'create a blog post about...' to write content")
    print("   - Say 'check my notifications' to see updates")

    while True:
        # Listen for voice input
        user_input = listen()

        if not user_input:
            continue

        # Check for exit commands
        if user_input.lower() in ["quit", "exit", "stop", "goodbye", "bye"]:
            speak("Goodbye! Have a great day!")
            break

        # Process with LLM and MCP tools
        try:
            response = await process_with_llm(user_input, mcp_client, conversation_history)
            speak(response)
        except Exception as e:
            print(f"❌ Error: {e}")
            speak("Sorry, I encountered an error processing your request.")


if __name__ == "__main__":
    asyncio.run(main())
