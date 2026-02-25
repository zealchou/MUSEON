# MuseClaw

A living AI assistant with 44 skills that grows alongside you.

## Architecture

MuseClaw is built on:
- **Gateway Core**: 24/7 daemon with session management, cron engine, and security gate
- **LLM Client**: Claude Haiku + Sonnet dual-model smart routing
- **Memory Engine**: Four-channel memory with vector indexing
- **Agent Runtime**: Tool execution with sandbox isolation

## Installation

```bash
cd museclaw
pip install -e ".[dev]"
```

## Development

Run tests:
```bash
pytest tests/ -v
```

Run with coverage:
```bash
pytest tests/ -v --cov=museclaw --cov-report=html
```

## License

Proprietary - Zeal's Consulting Clients Only
