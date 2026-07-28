# Pundit AI

Pundit AI is a football (soccer) AI analyst, built as a portfolio project combining agentic AI architecture, data engineering, and applied machine learning in one system. The core thesis is that the AI should form its own opinion from underlying stats when a user asks a question, not just report numbers back — asking "did Marquinhos play well yesterday" should get a judgment ("yes, he played well overall - 4 tackles, strong duel win rate - but had a mistake that led to a goal"), not a stat dump.

## Setup

1. Create a virtual environment:
   ```
   python -m venv venv
   ```
2. Activate it, then install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your real API keys and database URL:
   ```
   cp .env.example .env
   ```
