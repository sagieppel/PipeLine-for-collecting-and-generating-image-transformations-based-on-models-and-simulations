"""Small OpenRouter client used by the dataset-generation scripts.

The transformation generators use this module for two kinds of LLM calls:

1. Plain text prompts, usually to suggest or inspect transformation ideas.
2. Optional image+text prompts, where local image files are sent as base64 data
   URLs in OpenRouter's OpenAI-compatible chat-completions format.

Most callers use ``get_reponse`` (name kept for compatibility with the existing
codebase), which appends prompts and responses to the shared ``data['messages']``
log when a state dictionary is provided.
"""

import ast
import base64
import json
import mimetypes
import time
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional, Union

import requests

import API_KEYS


def get_mime_type(path: str) -> str:
    """Return the MIME type for an image path, falling back to raw bytes."""
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def normalize_to_json(raw: str) -> str:
    """Normalize model output into a string that ``json.loads`` can parse.

    Models sometimes wrap JSON in Markdown code fences, or return a Python-like
    literal with single quotes. This helper strips fences, accepts valid JSON
    directly, and falls back to ``ast.literal_eval`` for Python literals.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 1)[1]
        text = text.rsplit("```", 1)[0]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()

    try:
        obj = json.loads(text)
    except JSONDecodeError:
        obj = ast.literal_eval(text)
    return json.dumps(obj)


def get_reponse(data=None, text=None, messages=None, model="", as_json=False):
    """Call the model and optionally append the exchange to ``data``.

    The misspelled function name is kept because the rest of the repository
    imports it as ``get_reponse``.
    """
    if messages is None:
        messages = []
    if text is not None:
        print("\n\n\nQuery:\n" + text + "\n")

    result = get_response_image_txt_json(
        text=text,
        model=model,
        as_json=as_json,
        messages=messages,
    )
    if data is None:
        return result

    data["messages"].append({"role": "user", "content": text})
    data["messages"].append({"role": "system", "content": str(result)})
    return result, data


def get_response_image_txt_json(
    text: str = None,
    img_path: Optional[Union[List[str], Dict[str, str]]] = None,
    model: str = "gpt-5-mini",
    as_json: bool = True,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> Any:
    """Retry an OpenRouter request a few times before surfacing the error."""
    if messages is None:
        messages = []

    original_message_count = len(messages)
    last_error = None
    for _ in range(5):
        retry_messages = messages[:original_message_count]
        try:
            return get_response_image_txt_json_openrouter(
                text=text,
                img_path=img_path,
                model=model,
                as_json=as_json,
                messages=retry_messages,
            )
        except Exception as error:
            last_error = error
            print(
                "Error getting answer:\n",
                error,
                "\nModel:",
                model,
                "\nmight be model, key or token issue ",
            )
            print("sleeping 6 seconds and try again")
            time.sleep(6)

    raise RuntimeError(f"Failed to get model response after retries: {last_error}")


def get_response_image_txt_json_openrouter(
    text: str,
    img_path: Optional[Union[List[str], Dict[str, str]]] = None,
    model: str = "qwen/qwen2.5-vl-72b-instruct",
    as_json: bool = True,
    messages: Optional[List[Dict[str, Any]]] = None,
    api_key: Optional[str] = None,
    site_url: Optional[str] = None,
    app_name: Optional[str] = None,
    timeout: int = 120,
) -> Any:
    """Send a text or image+text chat-completion request through OpenRouter.

    Args:
        text: Prompt text to send as the user message.
        img_path: Optional list of image paths, or mapping from label to image
            path. Images are embedded as base64 data URLs.
        model: OpenRouter model slug.
        as_json: When true, request JSON mode and parse the response.
        messages: Existing chat history to include before the new user content.
        api_key: Explicit OpenRouter API key. Defaults to ``API_KEYS``.
        site_url: Optional OpenRouter attribution URL.
        app_name: Optional OpenRouter attribution title.
        timeout: HTTP request timeout in seconds.

    Returns:
        Parsed JSON when ``as_json`` is true, otherwise the raw model text.
    """
    if api_key is None:
        api_key = API_KEYS.openrouter_api_key
    if api_key is None:
        raise ValueError("api_key is required (your OpenRouter API key).")
    if messages is None:
        messages = []

    content: List[Dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})

    if img_path:
        if isinstance(img_path, dict):
            items = list(img_path.items())
        else:
            items = [(f"image_{i}", path) for i, path in enumerate(img_path)]

        for label, path in items:
            with open(path, "rb") as image_file:
                b64 = base64.b64encode(image_file.read()).decode("utf-8")

            mime = get_mime_type(path)
            content.append({"type": "text", "text": f"This is image {label}:"})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )

    payload_messages = list(messages)
    if content:
        payload_messages.append({"role": "user", "content": content})

    if as_json:
        payload_messages.append(
            {
                "role": "user",
                "content": (
                    "Respond with raw JSON only. Do not use Markdown. "
                    "Do not wrap the response in code fences. Output must be "
                    "directly parsable by JSON.parse."
                ),
            }
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name

    payload: Dict[str, Any] = {
        "model": model,
        "messages": payload_messages,
    }
    if as_json:
        payload["response_format"] = {"type": "json_object"}

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        data=json.dumps(payload),
        timeout=timeout,
    )
    response.raise_for_status()
    response_data = response.json()

    message = response_data["choices"][0]["message"]["content"]
    if as_json:
        return json.loads(normalize_to_json(message))
    return message
