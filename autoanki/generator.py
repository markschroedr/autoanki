from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import CUSTOM_PROMPT_PATH
from .text_clean import clean_cards, clean_source


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
GEMINI_MODELS_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
DEFAULT_PROVIDER = "openrouter"
DEFAULT_OPENROUTER_MODEL = "google/gemini-3.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_TARGET_CARD_COUNT = 3
MAX_TARGET_CARD_COUNT = 12
DEFAULT_TAGS = [
    "concept",
    "definition",
    "formula",
    "process",
    "comparison",
    "example",
    "mistake",
    "workflow",
]
JSON_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
CJK_CHARACTERS = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af"
UNEXPECTED_CJK = re.compile(fr"[{CJK_CHARACTERS}]")
UNICODE_GLITCH_WARNING = (
    "Unicode-Check: Unerwartete CJK-Zeichen in der Modellantwort erkannt; "
    "bitte die Ausgabe vor dem Speichern prüfen."
)
MAX_CUSTOM_PROMPT_LENGTH = 20_000


def load_custom_prompt(path: str | Path = CUSTOM_PROMPT_PATH) -> str:
    file_path = Path(path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8-sig").strip()


def save_custom_prompt(value: str, path: str | Path = CUSTOM_PROMPT_PATH) -> Path:
    text = value.replace("\r\n", "\n").strip()
    if len(text) > MAX_CUSTOM_PROMPT_LENGTH:
        raise ValueError(f"Custom prompt must be at most {MAX_CUSTOM_PROMPT_LENGTH:,} characters.")
    file_path = Path(path)
    if not text:
        file_path.unlink(missing_ok=True)
        return file_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text + "\n", encoding="utf-8")
    return file_path


def configured_tags() -> list[str]:
    raw_tags = os.environ.get("AUTOANKI_TAGS", "")
    tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
    return tags or list(DEFAULT_TAGS)


def configured_target_card_count() -> int:
    raw_value = os.environ.get("AUTOANKI_TARGET_CARD_COUNT", str(DEFAULT_TARGET_CARD_COUNT)).strip()
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_TARGET_CARD_COUNT
    return min(MAX_TARGET_CARD_COUNT, max(1, value))


def card_schema(tags: list[str] | None = None, max_cards: int | None = None) -> dict[str, Any]:
    tag_values = tags or configured_tags()
    card_limit = max_cards or configured_target_card_count()
    return {
        "type": "object",
        "properties": {
            "note_to_user": {
                "type": "string",
                "maxLength": 280,
                "description": "Empty unless the source is genuinely unclear, insufficient, contradictory, or appears factually wrong.",
            },
            "cards": {
                "type": "array",
                "maxItems": card_limit,
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["basic", "cloze"]},
                        "front": {"type": "string"},
                        "back": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "maxItems": 2,
                            "items": {"type": "string", "enum": tag_values},
                        },
                    },
                    "required": ["type", "front", "back", "tags"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["note_to_user", "cards"],
        "additionalProperties": False,
    }


@dataclass
class GenerationResult:
    cards: list[dict[str, Any]]
    note_to_user: str = ""


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key_env: str
    model_env: str
    default_model: str | None = None
    base_url: str | None = None
    docs_url: str = ""
    setup_hint: str = ""
    supports_images: bool = True
    uses_strict_schema: bool = False
    extra_headers: dict[str, str] = field(default_factory=dict)


PROVIDERS: dict[str, ProviderConfig] = {
    "openrouter": ProviderConfig(
        name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        model_env="OPENROUTER_MODEL",
        default_model=DEFAULT_OPENROUTER_MODEL,
        base_url=OPENROUTER_URL,
        docs_url="https://openrouter.ai/docs",
        setup_hint="Best default if you want one key for Gemini, Claude, OpenAI, and many open models.",
        uses_strict_schema=True,
        extra_headers={
            "HTTP-Referer": "https://github.com/markschroedr/autoanki",
            "X-Title": "AutoAnki",
        },
    ),
    "openai": ProviderConfig(
        name="openai",
        api_key_env="OPENAI_API_KEY",
        model_env="OPENAI_MODEL",
        base_url=OPENAI_URL,
        docs_url="https://platform.openai.com/docs",
        setup_hint="Use this if you already have OpenAI API billing enabled. Set OPENAI_MODEL explicitly.",
        uses_strict_schema=True,
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        model_env="ANTHROPIC_MODEL",
        default_model=DEFAULT_ANTHROPIC_MODEL,
        base_url=ANTHROPIC_URL,
        docs_url="https://docs.anthropic.com/en/api/messages",
        setup_hint="Use this for first-party Claude access.",
    ),
    "gemini": ProviderConfig(
        name="gemini",
        api_key_env="GEMINI_API_KEY",
        model_env="GEMINI_MODEL",
        default_model=DEFAULT_GEMINI_MODEL,
        docs_url="https://ai.google.dev/gemini-api/docs",
        setup_hint="Use this for first-party Google AI Studio / Gemini API access.",
    ),
}


def load_dotenv(path: str | Path = ".env") -> None:
    file_path = resolve_runtime_path(path)
    if file_path is None:
        return
    for raw_line in file_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def writable_runtime_path(path: str | Path = ".env") -> Path:
    file_path = Path(path)
    if file_path.is_absolute():
        return file_path
    existing_path = resolve_runtime_path(file_path)
    if existing_path is not None:
        return existing_path
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / file_path
    return Path.cwd() / file_path


def resolve_runtime_path(path: str | Path, must_exist: bool = True) -> Path | None:
    file_path = Path(path)
    if file_path.is_absolute():
        return file_path if file_path.exists() or not must_exist else None

    candidates = [Path.cwd() / file_path]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / file_path)
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(Path(bundle_dir) / file_path)
    candidates.append(Path(__file__).resolve().parent / file_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None if must_exist else candidates[0]


def update_dotenv_values(updates: dict[str, str], path: str | Path = ".env") -> Path:
    file_path = writable_runtime_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    lines = file_path.read_text(encoding="utf-8-sig").splitlines() if file_path.exists() else []
    remaining = dict(updates)
    rendered: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            rendered.append(raw_line)
            continue
        key = raw_line.split("=", 1)[0].strip()
        if key in remaining:
            rendered.append(f"{key}={remaining.pop(key)}")
        else:
            rendered.append(raw_line)
    if remaining and rendered and rendered[-1].strip():
        rendered.append("")
    for key, value in remaining.items():
        rendered.append(f"{key}={value}")
    file_path.write_text("\n".join(rendered).rstrip() + "\n", encoding="utf-8")
    return file_path


def configured_provider_name() -> str:
    value = os.environ.get("AUTOANKI_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    if value not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise RuntimeError(f"Unknown AUTOANKI_PROVIDER '{value}'. Use one of: {known}")
    return value


def provider_config(provider: str | None = None) -> ProviderConfig:
    load_dotenv()
    name = (provider or configured_provider_name()).strip().lower()
    if name not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise RuntimeError(f"Unknown provider '{name}'. Use one of: {known}")
    return PROVIDERS[name]


def set_provider_model(
    provider: str,
    model: str,
    target_card_count: str | int | None = None,
    path: str | Path = ".env",
) -> Path:
    load_dotenv(path)
    name = provider.strip().lower()
    if name not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise RuntimeError(f"Unknown provider '{provider}'. Use one of: {known}")
    config = PROVIDERS[name]
    clean_model = model.strip() or config.default_model or ""
    if not clean_model:
        raise RuntimeError(f"{config.model_env} is required for {name}")
    os.environ["AUTOANKI_PROVIDER"] = name
    os.environ[config.model_env] = clean_model
    updates = {"AUTOANKI_PROVIDER": name, config.model_env: clean_model}
    if target_card_count is not None:
        try:
            raw_count = int(str(target_card_count).strip())
        except ValueError as exc:
            raise RuntimeError("Target card count must be an integer") from exc
        count = min(MAX_TARGET_CARD_COUNT, max(1, raw_count))
        os.environ["AUTOANKI_TARGET_CARD_COUNT"] = str(count)
        updates["AUTOANKI_TARGET_CARD_COUNT"] = str(count)
    return update_dotenv_values(updates, path=path)


def provider_status() -> list[dict[str, Any]]:
    load_dotenv()
    active = configured_provider_name()
    rows = []
    for name, config in PROVIDERS.items():
        key_set = bool(os.environ.get(config.api_key_env))
        model = os.environ.get(config.model_env) or config.default_model or ""
        rows.append(
            {
                "name": name,
                "active": name == active,
                "api_key_env": config.api_key_env,
                "model_env": config.model_env,
                "model": model,
                "key_set": key_set,
                "docs_url": config.docs_url,
                "setup_hint": config.setup_hint,
                "target_card_count": configured_target_card_count(),
            }
        )
    return rows


def list_provider_models(provider: str | None = None) -> list[str]:
    config = provider_config(provider)
    if config.name == "openrouter":
        request = urllib.request.Request(OPENROUTER_URL.replace("/chat/completions", "/models"), method="GET")
    elif config.name == "openai":
        if not os.environ.get(config.api_key_env):
            raise RuntimeError(f"{config.api_key_env} is required to list OpenAI models")
        request = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {os.environ[config.api_key_env]}"},
            method="GET",
        )
    elif config.name == "anthropic":
        if not os.environ.get(config.api_key_env):
            raise RuntimeError(f"{config.api_key_env} is required to list Anthropic models")
        request = urllib.request.Request(
            ANTHROPIC_MODELS_URL,
            headers={
                "x-api-key": os.environ[config.api_key_env],
                "anthropic-version": "2023-06-01",
            },
            method="GET",
        )
    elif config.name == "gemini":
        if not os.environ.get(config.api_key_env):
            raise RuntimeError(f"{config.api_key_env} is required to list Gemini models")
        url = GEMINI_MODELS_URL_TEMPLATE.format(api_key=urllib.parse.quote(os.environ[config.api_key_env], safe=""))
        request = urllib.request.Request(url, method="GET")
    else:
        raise RuntimeError(f"Provider '{config.name}' cannot list models")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{config.name} model list failed ({exc.code}): {body}") from exc

    if config.name == "gemini":
        models = []
        for item in data.get("models", []):
            methods = item.get("supportedGenerationMethods") or []
            if methods and "generateContent" not in methods:
                continue
            name = str(item.get("name", ""))
            if name.startswith("models/"):
                name = name.removeprefix("models/")
            if name:
                models.append(name)
        return sorted(set(models))

    return sorted(
        {
            str(item.get("id", ""))
            for item in data.get("data", [])
            if isinstance(item, dict) and item.get("id")
        }
    )


def _parse_json_content(content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        text = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    else:
        text = str(content or "")
    text = text.strip()
    match = JSON_FENCE.match(text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


class CardGenerator:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        prompt_path: str | Path = "system_prompt.txt",
        custom_prompt_path: str | Path = CUSTOM_PROMPT_PATH,
        provider: str | None = None,
        timeout: int = 90,
    ) -> None:
        load_dotenv()
        self.config = provider_config(provider)
        self.api_key = api_key or os.environ.get(self.config.api_key_env)
        self.model = model or os.environ.get(self.config.model_env) or self.config.default_model
        self.prompt_path = prompt_path
        self.custom_prompt_path = Path(custom_prompt_path)
        self.timeout = timeout

    def generate(self, source: dict[str, Any], forced_tags: list[str] | None = None) -> list[dict[str, Any]]:
        return self.generate_result(source, forced_tags=forced_tags).cards

    def generate_result(self, source: dict[str, Any], forced_tags: list[str] | None = None) -> GenerationResult:
        if not self.api_key:
            raise RuntimeError(f"{self.config.api_key_env} is not set")
        if not self.model:
            raise RuntimeError(f"{self.config.model_env} is not set")

        source = clean_source(source)
        if self.config.name in {"openrouter", "openai"}:
            return self._generate_openai_compatible(source, forced_tags)
        if self.config.name == "anthropic":
            return self._generate_anthropic(source, forced_tags)
        if self.config.name == "gemini":
            return self._generate_gemini(source, forced_tags)
        raise RuntimeError(f"Provider '{self.config.name}' is not implemented")

    def _system_prompt(self) -> str:
        prompt_path = resolve_runtime_path(self.prompt_path)
        if prompt_path is None:
            raise RuntimeError(f"Prompt file not found: {self.prompt_path}")
        prompt = prompt_path.read_text(encoding="utf-8")
        subject = os.environ.get("AUTOANKI_SUBJECT", "the supplied material").strip() or "the supplied material"
        tags = ", ".join(configured_tags())
        target_count = configured_target_card_count()
        rendered = (
            f"{prompt}\n\n"
            f"Configured subject hint: {subject}.\n"
            f"Allowed tags: {tags}.\n"
            f"Target card count: aim for about {target_count} card(s) when the material supports it. "
            "Return fewer cards, or zero cards, when that is more appropriate.\n"
            "Use only the allowed tags above, at most two per card.\n"
        )
        custom_prompt = load_custom_prompt(self.custom_prompt_path)
        if custom_prompt:
            rendered += (
                "\nCustom instructions follow. Apply them only when they are compatible with all generic rules above; "
                "the generic output, safety, MathJax, and allowed-tag rules remain authoritative.\n\n"
                f"{custom_prompt}\n"
            )
        return rendered

    def _generate_openai_compatible(
        self,
        source: dict[str, Any],
        forced_tags: list[str] | None,
    ) -> GenerationResult:
        payload = self._openai_compatible_payload(source, forced_tags)
        request = urllib.request.Request(
            self.config.base_url or OPENAI_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                **self.config.extra_headers,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.config.name} request failed ({exc.code}): {body}") from exc

        content = response_data["choices"][0]["message"]["content"]
        return self._generation_from_parsed(_parse_json_content(content), source)

    def _generate_anthropic(self, source: dict[str, Any], forced_tags: list[str] | None) -> GenerationResult:
        payload = self._anthropic_payload(source, forced_tags)
        request = urllib.request.Request(
            ANTHROPIC_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": str(self.api_key),
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"anthropic request failed ({exc.code}): {body}") from exc
        text = "".join(
            part.get("text", "")
            for part in response_data.get("content", [])
            if isinstance(part, dict) and part.get("type") == "text"
        )
        return self._generation_from_parsed(_parse_json_content(text), source)

    def _generate_gemini(self, source: dict[str, Any], forced_tags: list[str] | None) -> GenerationResult:
        payload = self._gemini_payload(source, forced_tags)
        url = GEMINI_URL_TEMPLATE.format(
            model=urllib.parse.quote(str(self.model), safe=""),
            api_key=urllib.parse.quote(str(self.api_key), safe=""),
        )
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"gemini request failed ({exc.code}): {body}") from exc
        candidates = response_data.get("candidates") or []
        parts = (((candidates[0] or {}).get("content") or {}).get("parts") or []) if candidates else []
        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        return self._generation_from_parsed(_parse_json_content(text), source)

    def _generation_from_parsed(self, parsed: dict[str, Any], source: dict[str, Any] | None = None) -> GenerationResult:
        cards = clean_cards(parsed.get("cards", []))
        note_to_user = str(parsed.get("note_to_user") or "").strip()
        source_text = str((source or {}).get("text") or "")
        model_output = json.dumps({"note_to_user": note_to_user, "cards": cards}, ensure_ascii=False)
        if UNEXPECTED_CJK.search(model_output) and not UNEXPECTED_CJK.search(source_text):
            note_to_user = f"{note_to_user}\n\n{UNICODE_GLITCH_WARNING}".strip()
        return GenerationResult(
            cards=cards,
            note_to_user=note_to_user,
        )

    def _base_text_parts(self, source: dict[str, Any], forced_tags: list[str] | None) -> list[str]:
        parts = []
        text = source.get("text")
        if text:
            parts.append(str(text))
        if forced_tags:
            parts.append(f"Use only these tags if suitable: {', '.join(forced_tags)}")
        if not parts:
            parts.append("No source text was provided. Use any attached image if present.")
        return parts

    def _openai_content_parts(self, source: dict[str, Any], forced_tags: list[str] | None) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        for text in self._base_text_parts(source, forced_tags):
            parts.append({"type": "text", "text": text})
        image_b64 = source.get("image_b64")
        if image_b64:
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                }
            )
        return parts

    def _openai_compatible_payload(self, source: dict[str, Any], forced_tags: list[str] | None) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._openai_content_parts(source, forced_tags)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "anki_cards",
                    "strict": True,
                    "schema": card_schema(max_cards=configured_target_card_count()),
                },
            },
        }

    def _anthropic_payload(self, source: dict[str, Any], forced_tags: list[str] | None) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": text} for text in self._base_text_parts(source, forced_tags)]
        image_b64 = source.get("image_b64")
        if image_b64:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                }
            )
        return {
            "model": self.model,
            "max_tokens": 1600,
            "system": self._system_prompt(),
            "messages": [{"role": "user", "content": content}],
        }

    def _gemini_payload(self, source: dict[str, Any], forced_tags: list[str] | None) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"text": text} for text in self._base_text_parts(source, forced_tags)]
        image_b64 = source.get("image_b64")
        if image_b64:
            parts.append({"inlineData": {"mimeType": "image/png", "data": image_b64}})
        return {
            "systemInstruction": {"parts": [{"text": self._system_prompt()}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json"},
        }


OpenRouterCardGenerator = CardGenerator


def image_to_b64(image: Any) -> str:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
