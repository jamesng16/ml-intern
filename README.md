<p align="center">
  <img src="frontend/public/smolagents_kaggle.png" alt="smolagents logo" width="160" />
</p>

<p align="center">
    <a href="https://github.com/huggingface/ml-intern/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
    <a href="https://smolagents-ml-intern.hf.space/"><img alt="Website" src="https://img.shields.io/website/https/smolagents-ml-intern.hf.space.svg?down_color=red&down_message=offline&up_message=online"></a>
</p>

# ML Intern Kaggle Pro

An autonomous ML agent that researches, trains, and competes on Kaggle — with full support for pushing notebooks to Kaggle GPUs, polling results, error recovery, and cross-session learning. Forked from [huggingface/ml-intern](https://github.com/huggingface/ml-intern) and extended with a complete Kaggle competition integration.

## What's New (vs upstream ml-intern)

### Kaggle Competition Integration
A full-loop autonomous Kaggle workflow built on top of the existing HuggingFace agent:

- **17 Kaggle operations** — browse competitions, read notebooks/discussions, push scripts to Kaggle GPUs, poll execution, download output, submit predictions, and track scores
- **Autonomous polling** — after pushing a notebook, the agent polls status at increasing intervals (5min → 10min → 15min) and auto-recovers from errors
- **Error recovery** — on notebook failure, downloads logs, reads working notebooks for solutions, fixes the script, and re-pushes
- **Cross-session learning** — run history persists at `~/.kaggle/agent_runs/`, so the agent remembers every error, fix, and score from previous sessions and never repeats the same mistake
- **Daily submission cap** — enforces 3 submissions/day to conserve quota; excess time goes to research
- **Runtime pitfall avoidance** — hard-won lessons about Kaggle mount paths, GPU accelerators, BYOD docker images, offline packages, and cutlass dependencies are baked into the system prompt

### New Files

| File | Purpose |
|------|---------|
| `agent/tools/kaggle_tool.py` | Core Kaggle tool — 17 operations (list, read, push, poll, submit, save_run, run_history) with httpx REST + score/run log persistence |
| `agent/tools/kaggle_notebooks.py` | Notebook generation utility — creates competition notebooks with nbformat |
| `tests/unit/test_kaggle_tool.py` | Unit tests for auth, score persistence, dispatch, approval gates |
| `kaggle_nemotron/` | Working example: NVIDIA Nemotron Reasoning Challenge baseline |

### Modified Files

| File | Change |
|------|--------|
| `agent/core/tools.py` | Registered kaggle tool in `create_builtin_tools()` |
| `agent/core/agent_loop.py` | Added approval gates for `submit` and `push_notebook` |
| `agent/tools/research_tool.py` | Added kaggle to research sub-agent tools + hints |
| `agent/prompts/system_prompt_v3.yaml` | Added autonomous Kaggle workflow (5 phases) + 8 runtime pitfalls |

## Kaggle Operations

| Operation | Description | Approval |
|-----------|-------------|----------|
| `list_competitions` | Browse active competitions | No |
| `competition_details` | Get eval metric, deadline, rules | No |
| `list_data_files` | List competition data files | No |
| `list_notebooks` | Find top notebooks (by votes/score/date) | No |
| `read_notebook` | Read full notebook source as markdown | No |
| `notebook_metadata` | Get exact sources, accelerator, docker image from working notebooks | No |
| `list_discussions` | Browse competition forum | No |
| `read_discussion` | Read discussion with replies | No |
| `leaderboard` | View top leaderboard entries | No |
| `my_submissions` | List your submissions + scores | No |
| `submit` | Submit from kernel output (`-k notebook -v version`) or local file | **Yes** |
| `push_notebook` | Push script to Kaggle GPU and run it | **Yes** |
| `notebook_status` | Poll execution status | No |
| `notebook_log` | View live/partial execution log of a running kernel | No |
| `notebook_output` | Download output files/logs | No |
| `score_history` | Local score tracking with trend analysis | No |
| `save_run` | Log a run event (push, error, fix, submission) | No |
| `run_history` | View full run log — errors, fixes, scores | No |

## Autonomous Kaggle Workflow

The agent follows a 5-phase loop for each competition:

```
Phase 0: Session Startup
  └─ Read run_history (avoid past mistakes) + check daily submission count

Phase 1: Competition Analysis (first time)
  └─ Details, data files, leaderboard, notebook_metadata from official demo

Phase 2: Research (every session)
  └─ Check for new top notebooks, read latest 3-5 discussions, deep paper research

Phase 3: Implement & Push
  └─ Write script with pre-flight checklist → push_notebook with correct
     accelerator, docker_image, sources from notebook_metadata

Phase 4: Poll & Recover
  └─ 5min → 10min → 15min polling
  └─ On error: download logs → analyze → fix → re-push → log via save_run
  └─ On success: submit directly from kernel output (no download needed)

Phase 5: Iterate
  └─ Check score → analyze → research new ideas → implement next version
  └─ Max 3 submissions/day enforced
```

## Competition Memory

The agent maintains persistent memory across sessions so it never starts from scratch:

```
~/.kaggle/
  ├─ agent_runs/
  │   └─ {competition}.json      ← every push, error, fix, and submission with timestamps
  └─ agent_scores/
      └─ {competition}.json      ← score history with trend analysis
```

**What gets remembered:**
- Every notebook push (version, hypothesis, result)
- Every error with its exact message and the fix that resolved it
- Every submission with its hypothesis and score
- Research notes (approaches found in top notebooks and discussions)

**How it's used on session restart:**
1. Agent reads `run_history` first — sees all past errors and their fixes, so it never repeats the same mistake (e.g. wrong GPU, missing cutlass, bad data path)
2. Checks `score_history` — knows the current best score and whether the trend is improving
3. Checks `my_submissions` — knows how many of today's 3 submission slots are used
4. Compares current top notebooks against what it already tried — only pursues new ideas

This means session 2 picks up exactly where session 1 left off, and session 10 has the accumulated knowledge of all 9 sessions before it.

---

## Quick Start

### Installation

```bash
git clone https://github.com/adityaghai07/ml-intern-kaggle-pro.git
cd ml-intern-kaggle-pro
pip install -e ".[dev]"
```

### Environment Setup

Create a `.env` file:

```bash
ANTHROPIC_API_KEY=<your-anthropic-api-key>
HF_TOKEN=<your-hugging-face-token>
KAGGLE_USERNAME=<your-kaggle-username>
KAGGLE_KEY=<your-kaggle-api-key>
```

Get Kaggle credentials from [kaggle.com/settings → API](https://www.kaggle.com/settings) or place `kaggle.json` at `~/.kaggle/kaggle.json`.

All API-based model calls go through Hugging Face [Inference Providers](https://huggingface.co/docs/inference-providers/en/index), so your `HF_TOKEN` must be allowed to make Inference Provider calls. If no `HF_TOKEN` is set, the CLI will prompt you to paste one on first launch unless you start on a local model. To get a `GITHUB_TOKEN` follow the tutorial [here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token). See the [local models section below](#local-models) for instructions on using agents that run on your hardware.

### Usage

#### Interactive mode (start a chat session):

```bash
ml-intern
```

#### Headless mode (single prompt, auto-approve):

```bash
# Run a competition autonomously
ml-intern "compete on nvidia-nemotron-model-reasoning-challenge"

# With specific model
ml-intern --model anthropic/claude-sonnet-4-6 "compete on titanic"
```

**Options:**

```bash
ml-intern --sandbox-tools "your prompt"                         # use HF Space sandbox tools
ml-intern --max-iterations 100 "your prompt"
ml-intern --no-stream "your prompt"
# Change model
ml-intern --model moonshotai/Kimi-K2.7-Code:novita "your prompt"
ml-intern --model openai/gpt-5.5:fal-ai "your prompt"
```

Run `ml-intern` then `/model` to see the full list of suggested model ids
(Claude, GPT, HF Router models like MiniMax, Kimi, GLM, DeepSeek, and local
model prefixes).

Hosted inference is billed to the active Hugging Face user. See below on how to run `ml-intern` with local models.

#### Local models

Local model support uses OpenAI-compatible HTTP endpoints through LiteLLM. The
agent does not load model weights directly from disk; start your inference
server first, then select it with a provider-specific model prefix:

```bash
ml-intern --model ollama/llama3.1:8b "your prompt"
ml-intern --model vllm/meta-llama/Llama-3.1-8B-Instruct "your prompt"
```

Inside interactive mode, switch with `/model`:

```text
/model ollama/llama3.1:8b
/model lm_studio/google/gemma-3-4b
/model llamacpp/llama-3.1-8b-instruct
```

Supported local prefixes are `ollama/`, `vllm/`, `lm_studio/`, and
`llamacpp/`.

```bash
LOCAL_LLM_BASE_URL=http://localhost:8000
LOCAL_LLM_API_KEY=<optional-local-api-key>
```

Set `LOCAL_LLM_BASE_URL` and optional `LOCAL_LLM_API_KEY` to use one shared
local endpoint, or override a specific provider with its matching `*_BASE_URL`
/ `*_API_KEY` variable, such as `OLLAMA_BASE_URL` or `VLLM_API_KEY`.
Provider-specific variables take precedence over the shared local variables.
Base URLs may include or omit `/v1`.

**CLI tool runtime:**

By default, the CLI runs `bash`, `read`, `write`, and `edit` on your local
filesystem. To use HF Space sandbox tools instead, including `sandbox_create`,
opt in with `--sandbox-tools`:

```bash
ml-intern --sandbox-tools "test this training script in a GPU sandbox"
ml-intern --model llamacpp/ggml-org/gemma-3-1b-it-GGUF --sandbox-tools
```

Sandbox tool runtime requires `HF_TOKEN`, even when the selected model is local,
because it creates private HF Spaces. You can also make sandbox tools your CLI
default in `~/.config/ml-intern/cli_agent_config.json`:

```json
{ "tool_runtime": "sandbox" }
```

Use the default local runtime when you want tools to inspect or edit files in
your checkout. Use sandbox runtime when you want the agent to create or replace
an HF Space sandbox, test code remotely, or request GPU sandbox hardware before
launching larger HF Jobs.

## Example: NVIDIA Nemotron Reasoning Challenge

See `kaggle_nemotron/` for a complete working example. The agent:

1. Analyzed the competition (adapter submission, Nemotron-3-Nano-30B model, LoRA rank 32 max)
2. Read 3+ top notebooks to extract the winning recipe (CoT labels, 2048 seq len, 2 epochs)
3. Wrote `train_adapter.py` with all Kaggle runtime patches (cutlass, Triton, RMSNorm)
4. Pushed to Kaggle with correct GPU (`NvidiaRtxPro6000`) and competition docker image
5. Recovered from 4 runtime errors autonomously:
   - Missing cutlass → `site.addsitedir()` from utility script
   - OOM on P100 → switched to RTX Pro 6000 via `notebook_metadata`
   - No internet in BYOD image → offline package installation
   - Wrong offline packages path → recursive search at correct mount point

## Sharing Traces

Every session is auto-uploaded to your **own private Hugging Face dataset**
in [Claude Code JSONL format](https://huggingface.co/changelog/agent-trace-viewer),
which the HF Agent Trace Viewer auto-detects so you can browse turns, tool
calls, and model responses directly on the Hub.

By default the dataset is named `{your-hf-username}/ml-intern-sessions` and is
**created private**. You can flip it to public from inside the CLI:

```bash
/share-traces            # show current visibility + dataset URL
/share-traces public     # publish (anyone can view)
/share-traces private    # lock it back down
```

You can also flip visibility from the dataset page on huggingface.co — the
agent honours whatever you set there for subsequent uploads.

To opt out entirely, set in your CLI config (e.g. `configs/cli_agent_config.json`
or `~/.config/ml-intern/cli_agent_config.json`):

```json
{ "share_traces": false }
```

To override the destination repo, set:

```json
{ "personal_trace_repo_template": "{hf_user}/my-custom-traces" }
```

The shared `smolagents/ml-intern-sessions` dataset is unrelated and only
receives anonymized telemetry rows used by the backend KPI scheduler.

## Supported Gateways

ML Intern currently supports one-way notification gateways from CLI sessions.
These gateways send out-of-band status updates; they do not accept inbound chat
messages.

### Slack

Slack notifications use the Slack Web API to post messages when the agent needs
approval, hits an error, or completes a turn. Create a Slack app with a bot token
that has `chat:write`, invite the bot to the target channel, then set:

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C...
```

The CLI automatically creates a `slack.default` destination when both variables
are present. Optional environment variables for the env-only default:

```bash
ML_INTERN_SLACK_NOTIFICATIONS=false
ML_INTERN_SLACK_DESTINATION=slack.ops
ML_INTERN_SLACK_AUTO_EVENTS=approval_required,error,turn_complete
ML_INTERN_SLACK_ALLOW_AGENT_TOOL=true
ML_INTERN_SLACK_ALLOW_AUTO_EVENTS=true
```

For a persistent user-level config, put overrides in
`~/.config/ml-intern/cli_agent_config.json` or point `ML_INTERN_CLI_CONFIG` at a
JSON file:

```json
{
  "messaging": {
    "enabled": true,
    "auto_event_types": ["approval_required", "error", "turn_complete"],
    "destinations": {
      "slack.ops": {
        "provider": "slack",
        "token": "${SLACK_BOT_TOKEN}",
        "channel": "${SLACK_CHANNEL_ID}",
        "allow_agent_tool": true,
        "allow_auto_events": true
      }
    }
  }
}
```

## Architecture

Inherits the upstream ml-intern architecture (async queue-based agent loop with LiteLLM) and adds:

```
ToolRouter
  ├─ HF docs & research
  ├─ HF repos, datasets, jobs, papers
  ├─ GitHub code search
  ├─ Sandbox & local tools
  ├─ Planning
  ├─ Kaggle tool (NEW)          ← 17 operations
  │   ├─ httpx REST client       ← read operations
  │   ├─ Kaggle kernels push     ← notebook execution
  │   ├─ Score persistence       ← ~/.kaggle/agent_scores/
  │   └─ Run log persistence     ← ~/.kaggle/agent_runs/
  └─ MCP server tools
```

## Development

### Pre-commit Checks

Run Ruff before every commit:

```bash
uv run ruff check .
uv run ruff format --check .
```

If the format check fails, run `uv run ruff format .` and re-run the checks
before committing.

### Running Tests

```bash
pytest tests/unit/test_kaggle_tool.py -v
```

### Adding Built-in Tools

Edit `configs/cli_agent_config.json` for CLI defaults, or
`configs/frontend_agent_config.json` for web-session defaults:

```json
{
  "model_name": "zai-org/GLM-5.2:novita",
  "mcpServers": {
    "your-server-name": {
      "transport": "http",
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${YOUR_TOKEN}"
      }
    }
  }
}
```

Note: Environment variables like `${YOUR_TOKEN}` are auto-substituted from `.env`.

### Adding Kaggle Operations

Edit `agent/tools/kaggle_tool.py`:
1. Add an async handler function: `async def _my_op(args, limit) -> ToolResult`
2. Register in `_OPERATIONS` dict
3. Update `KAGGLE_TOOL_SPEC` description and parameters

## Credits

- Forked from [huggingface/ml-intern](https://github.com/huggingface/ml-intern)
- Kaggle integration by [@adityaghai07](https://github.com/adityaghai07)

## Cite ml-intern
If you use `ml-intern` in your work, please cite it by using the following BibTeX entry or similar.
```bibtex
@Misc{ml-intern,
  title =        {ml-intern: an agent that autonomously researches, writes, and ships good quality ML related code using the Hugging Face ecosystem},
  author =       {Aksel Joonas Reedi, Henri Bonamy, Yoan Di Cosmo, Leandro von Werra, Lewis Tunstall},
  howpublished = {\url{https://github.com/huggingface/ml-intern}},
  year =         {2026}
}
```
