# Groq AI Integration — Progress & Handoff

## Done
1. **Backup (verified):** `backups/pre_ai_integration_20261026_184904/` in the project root.
   It holds all source, templates, static files, requirements, `database.sql`, `.env.example`, `README.md`, and
   `database/demo_data_sqlite_dump.sql` (password columns removed). No `.env` or keys are included.
   `backups/` was added to `.gitignore`. MySQL could not be reached from Claude's shell, so export it yourself:
   Workbench → Server → Data Export → `business_finance_db`.
2. **Inspection:** the "AI Analysis" tab is `/insights` (`templates/insights.html`, route `insights()` in `app.py`). It shows **rule-based**
   recommendations from `analytics._recommendations()`. Real calculations: forecast = scikit-learn LinearRegression ×
   seasonal index; anomalies = robust Z-score; health score = deterministic 5×20 points. There was **no** chatbot or API.
3. **`ai_service.py` (new, complete, untested live):** a Groq client with a timeout, safe error messages, a per-user rate limiter,
   topic detection → `build_context()` that builds labelled ACTUAL / FORECAST / RULE_BASED JSON from `analytics.load()` (with no
   customer PII), a system prompt, and these functions: `chat(question, history)`, `summary()`, `recommendations()`,
   `explain_anomaly(expense_id)`, `explain_forecast(product_id)`, `explain_health()`, `status()`, `check_rate(user)`.
   It uses the default model `openai/gpt-oss-20b` (a current production model on Groq), with `reasoning_effort=low` and `include_reasoning=False`.
   The **live API was NOT tested**: there is no key, and api.groq.com is blocked from Claude's sandbox.

## Not done yet
- Flask routes in `app.py`, the chat UI in `insights.html`, the explain buttons on the anomaly/forecast/health pages, the `.env.example`
  and `requirements.txt` updates, tests, and the README.

## Prompt for another AI tool
```
I have a Flask project (AI-Powered Business Finance and Inventory Analysis System). A backup already exists in
backups/pre_ai_integration_20261026_184904/ — do not delete it. A finished module ai_service.py is in the project
root (read it first; do not rewrite it). Complete the Groq integration with minimal changes:

1. requirements.txt: add `groq>=0.30`. .env.example: add `GROQ_API_KEY=your_groq_api_key_here` and
   `GROQ_MODEL=openai/gpt-oss-20b` (placeholders only). Make sure .gitignore contains .env and backups/.
2. app.py: `import ai_service`. Add JSON POST routes protected by the existing @login_required (staff only):
   /ai/chat {question, history[]} -> ai_service.chat; /ai/summary; /ai/recommendations;
   /ai/explain/anomaly/<int:expense_id>; /ai/explain/forecast/<int:product_id>; /ai/explain/health;
   and GET /ai/status. Call ai_service.check_rate(session["user_id"]) first. Catch ai_service.AIError ->
   jsonify({"error": e.message, "code": e.code}), e.status. Catch any other Exception -> generic 500 JSON
   (log with ai_service.mask(), never log the key). Pass ai_status=ai_service.status() to insights.html.
3. templates/insights.html (the AI Analysis tab): add at the top a card "Business AI Assistant", subtitle
   "Ask questions about your business data and get actionable insights." with: message history panel,
   distinct user/AI bubbles, textarea (Enter=send, Shift+Enter=newline, maxlength 1000), Send button
   disabled while waiting, typing/loading indicator, error bubble, Clear Chat button, 8 suggestion chips
   (summary of business performance; products at risk of running out; why expenses increased; products
   generating most revenue; actions to improve profitability; explain financial health score; what the
   sales trend suggests; unusual expenses to investigate) that send the question. Keep history in
   sessionStorage and send the last 8 messages. Render AI answers with a small safe markdown renderer:
   ESCAPE HTML FIRST, then handle **bold**, *italic*, `code`, headings, bullet/numbered lists, paragraphs.
   Never use innerHTML on unescaped text. If ai_status.configured is false show a notice how to set
   GROQ_API_KEY. Also add buttons "Generate AI summary" and "AI recommendations" that show the result in a
   panel. Keep the existing rule-based cards below. Responsive; reuse existing CSS variables/classes in
   static/style.css (.card, .btn, .chip, .badge) and add new CSS at the end of style.css.
4. Add an "Explain with AI" button: per row on templates/anomalies.html (expense_id), on
   templates/forecast.html for the selected product (cur.product_id), and on templates/health.html. Put shared
   JS in static/ai.js (fetch POST, JSON, show the answer in an inline panel, handle errors).
5. Tests (tests/test_ai.py, pytest, FORCE_SQLITE=1): mock ai_service._complete to return ("mock answer",
   "mock-model"); check that chat returns 200 for a logged-in staff user, 302/401 when logged out, a too-long
   question gives 400, a missing key gives a 503 not_configured error, and that the context for "which products are
   running out" contains FORECAST_model_estimates and no emails. Run all existing pages to make sure they still return 200.
6. README: how to get a key at console.groq.com/keys, put it in .env (never commit), pip install -r requirements.txt,
   then python app.py. Do not change analytics.py calculations. Do not let the model run SQL.
```
