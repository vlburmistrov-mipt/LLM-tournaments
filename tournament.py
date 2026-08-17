import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from openai import OpenAI
from itertools import combinations

MODELS = ["llama3.2:3b", "qwen2.5:3b", "gemma2:2b", "mistral:7b"]
# MODELS = ["llama3.2:3b", "qwen2.5:3b", "gemma2:2b"]
# MODELS = ["gemma4:26b", "gemma4:26b"]
ROUNDS_PER_MATCH = 10

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
RESULTS_DIR = Path("tournament_logs")

client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)

PAYOFFS = {
    ("COOPERATE", "COOPERATE"): (3, 3),
    ("DEFECT", "COOPERATE"): (5, 0),
    ("COOPERATE", "DEFECT"): (0, 5),
    ("DEFECT", "DEFECT"): (1, 1),
}

SYSTEM_PROMPT = """You are participating in an Iterated Prisoner's Dilemma.
Your goal is to maximize your total score over all rounds.

Rules:
- If both COOPERATE: you both get 3 points.
- If you DEFECT and the other COOPERATES: you get 5 points, other gets 0.
- If you COOPERATE and the other DEFECTS: you get 0 points, other gets 5.
- If both DEFECT: you both get 1 point.

Analyze the history of the game and choose your next action.
You must respond with ONLY ONE WORD: either 'COOPERATE' or 'DEFECT'. Do not add any explanation."""


class RunLogger:
    def __init__(self):
        self.lines = []

    def log(self, text: str = ""):
        print(text)
        self.lines.append(text)

    def save(self, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")

def get_decision(model: str, history: list) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if history:
        history_text = "Game history so far:\n"
        for r, (my_move, opp_move) in enumerate(history, 1):
            history_text += f"Round {r}: You chose {my_move}, Opponent chose {opp_move}\n"
        messages.append({"role": "user", "content": f"{history_text}\nWhat is your next move (COOPERATE or DEFECT)?"})
    else:
        messages.append({"role": "user", "content": "Round 1. What is your move (COOPERATE or DEFECT)?"})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
    )

    decision = (response.choices[0].message.content or "").strip().upper()
    if "COOPERATE" in decision:
        return "COOPERATE"
    elif "DEFECT" in decision:
        return "DEFECT"
    else:
        return "DEFECT"

def play_match(model_a, model_b, logger: RunLogger):
    history_a = []
    history_b = []
    score_a = 0
    score_b = 0

    logger.log(f"\nМатч: {model_a} против {model_b}")

    for round_num in range(1, ROUNDS_PER_MATCH + 1):
        move_a = get_decision(model_a, history_a)
        move_b = get_decision(model_b, history_b)

        history_a.append((move_a, move_b))
        history_b.append((move_b, move_a))

        pts_a, pts_b = PAYOFFS[(move_a, move_b)]
        score_a += pts_a
        score_b += pts_b

        logger.log(f" Раунд {round_num}: {model_a} [{move_a}] ({pts_a} pts) | {model_b} [{move_b}] ({pts_b} pts)")

    return score_a, score_b

def run_tournament():
    logger = RunLogger()
    run_started_at = datetime.now()
    run_id = run_started_at.strftime("%Y%m%d_%H%M%S")
    protocol_path = RESULTS_DIR / f"tournament_{run_id}.txt"

    logger.log(f"Запуск турнира: {run_started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.log(f"OpenAI-compatible base URL: {OPENAI_BASE_URL}")
    logger.log(f"Модели: {', '.join(MODELS)}")
    logger.log(f"Раундов на матч: {ROUNDS_PER_MATCH}")

    scores = {model: 0 for model in MODELS}

    for model_a, model_b in combinations(MODELS, 2):
        score_a, score_b = play_match(model_a, model_b, logger)
        scores[model_a] += score_a
        scores[model_b] += score_b

    logger.log("\n" + "="*50)
    logger.log("ИТОГОВЫЕ РЕЗУЛЬТАТЫ СИСТЕМЫ")
    logger.log("="*50)
    
    results = []
    for model in MODELS:
        results.append({
            "Модель": model,
            "Итоговые очки": scores[model]
        })
    
    df = pd.DataFrame(results).sort_values(by="Итоговые очки", ascending=False)
    logger.log(df.to_string(index=False))
    logger.log(f"\nОбщая совокупная польза всех агентов: {sum(scores.values())} очков")

    logger.log(f"\nПротокол сохранен: {protocol_path}")
    logger.save(protocol_path)

if __name__ == "__main__":
    run_tournament()