# AtlasOS Provider Configuration & Local AI Guide

AtlasOS utilizes an **Enterprise AI Execution Layer** that intelligently routes LLM queries between local inference (Ollama) and cloud APIs (OpenRouter, Anthropic, OpenAI, etc.) based on task complexity and confidence scores.

## Architecture

The AI Execution Layer consists of:
1. **AI Execution Planner**: Decides if an LLM is necessary. It checks deterministic rules, semantic cache, and manages confidence-based escalation.
2. **LLM Router**: Executes tasks based on a `registry.yaml` configuration, tracking metrics and triggering fallbacks.
3. **Model Registry**: A YAML file defining preferred and fallback models for different tasks (`entity_extraction`, `complex_reasoning`, etc.).

## Local Inference Setup (Ollama)

By default, AtlasOS is configured to use Ollama for bulk data extraction to save costs and reduce latency.

1. **Install Ollama**: Follow instructions at [ollama.com](https://ollama.com/).
2. **Download Preferred Models**:
   ```bash
   ollama run qwen2.5:3b
   ```
3. **Configure AtlasOS**: Ensure your `.env` contains:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5:3b
   ENABLE_LOCAL_FIRST=true
   ```

## Cloud Provider Setup

AtlasOS falls back to cloud providers when a task requires complex reasoning or when the local model's extraction confidence is below the threshold (`CONFIDENCE_THRESHOLD=0.92`).

Supported providers:
- `openrouter`
- `anthropic`
- `openai`
- `gemini`
- `groq`

Add your keys to `.env`:
```env
OPENROUTER_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

## Configuring the Model Registry

The routing logic is defined in `backend/llm/registry.yaml`. You can modify this file to change the primary and fallback models per task.

```yaml
entity_extraction:
  preferred:
    - provider: ollama
      model: qwen2.5:3b
  fallback:
    - provider: openrouter
      model: openrouter/free
```

## Embedding Configuration

By default, AtlasOS uses local embeddings via `sentence-transformers` for strict privacy. The default model is `BAAI/bge-m3`.

```env
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL_NAME=BAAI/bge-m3
```

## Troubleshooting

- **Low Confidence Loops**: If Ollama consistently returns low confidence, the AI Planner will route to the cloud fallback. If no cloud key is set, the extraction will fail. Ensure a fallback is configured in `registry.yaml`.
- **Ollama Connection Refused**: Verify Ollama is running (`curl http://localhost:11434/api/tags`).
