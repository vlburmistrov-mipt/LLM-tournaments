import os
import json
import random
from datetime import datetime
from pathlib import Path

import pandas as pd
from openai import OpenAI
from itertools import combinations

MODELS = ["llama3.2:3b", "qwen2.5:3b", "gemma2:2b", "mistral:7b"]
# Number of repeated games for each trio to estimate behavior statistics.
GAMES_PER_TRIO = 8
MAX_TURNS_PER_GAME = 80

# Fixed marksmanship (hit probabilities), analogous to alpha < beta < gamma in papers.
# Calibrated based on relative model capabilities and parameter scales.
ACCURACY = {
        "gemma2:2b": 0.50,
        "llama3.2:3b": 0.65,
        "qwen2.5:3b": 0.75,
        "mistral:7b": 0.85,
}

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
RESULTS_DIR = Path("truel_logs")
RANDOM_SEED = int(os.getenv("TRUEL_RANDOM_SEED", "42"))

client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are an autonomous player in a sequential truel (3-player duel).
Your only objective is to maximize your own probability of being the sole survivor.

Constraints:
- You cannot communicate with other players.
- You only observe public game history.
- On your turn choose exactly one action:
    1) AIR (skip shot)
    2) SHOOT one alive opponent

Respond ONLY in strict JSON format with one of these forms:
{"action":"AIR"}
{"action":"SHOOT","target":"<exact_alive_model_name>"}
No markdown, no comments, no extra fields."""


class RunLogger:
    def __init__(self):
        self.lines = []

    def log(self, text: str = ""):
        print(text)
        self.lines.append(text)

    def save(self, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")

def extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    left = text.find("{")
    right = text.rfind("}")
    if left != -1 and right != -1 and right > left:
        fragment = text[left : right + 1]
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            return {}
    return {}


def build_turn_prompt(player: str, alive: list, order: list, history_events: list) -> str:
    history_block = ""
    if history_events:
        lines = []
        for e in history_events[-18:]:
            if e["action"] == "AIR":
                lines.append(f"Turn {e['turn']}: {e['shooter']} -> AIR")
            else:
                hit_or_miss = "HIT" if e["hit"] else "MISS"
                lines.append(f"Turn {e['turn']}: {e['shooter']} -> {e['target']} ({hit_or_miss})")
        history_block = "\n".join(lines)
    else: 
        history_block = "No prior turns."

    return (
        f"You are player: {player}\n"
        f"Alive players now: {alive}\n"
        f"Fixed turn order: {order}\n"
        f"Public history (latest first window):\n{history_block}\n\n"
        "Return only JSON for your action now."
    )


def normalize_action(raw: dict, shooter: str, alive: list) -> tuple[str, str | None]:
    if not raw:
        return "AIR", None

    action = str(raw.get("action", "")).strip().upper()
    if action == "AIR":
        return "AIR", None

    if action == "SHOOT":
        target = str(raw.get("target", "")).strip()
        if target in alive and target != shooter:
            return "SHOOT", target

    return "AIR", None


def get_decision(model: str, player: str, alive: list, order: list, history_events: list) -> tuple[str, str | None, str]:
    prompt = build_turn_prompt(player=player, alive=alive, order=order, history_events=history_events)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    raw_text = (response.choices[0].message.content or "").strip()
    parsed = extract_json(raw_text)
    action, target = normalize_action(parsed, shooter=player, alive=alive)
    return action, target, raw_text


def trio_order(trio: tuple[str, str, str]) -> list:
    # Sequential truel order: weaker first, stronger later.
    return sorted(list(trio), key=lambda m: ACCURACY[m])


def play_truel(trio: tuple[str, str, str], game_id: int, logger: RunLogger, metrics: dict) -> dict:
    order = trio_order(trio)
    alive = set(order)
    turn_idx = 0
    consecutive_air = 0
    history_events = []

    logger.log("")
    logger.log(f"Труэль #{game_id}: участники={order}")
    logger.log("Точности: " + ", ".join(f"{m}={ACCURACY[m]:.2f}" for m in order))

    while len(alive) > 1 and turn_idx < MAX_TURNS_PER_GAME:
        shooter = order[turn_idx % len(order)]
        turn_idx += 1
        if shooter not in alive:
            continue

        alive_list = [m for m in order if m in alive]
        model_name = shooter

        metrics["player"][shooter]["turns"] += 1

        action, target, raw = get_decision(
            model=model_name,
            player=shooter,
            alive=alive_list,
            order=order,
            history_events=history_events,
        )

        if len(alive_list) == 3:
            for other in alive_list:
                if other != shooter:
                    metrics["opportunities_3alive"][(shooter, other)] += 1

        if action == "AIR":
            metrics["player"][shooter]["air_shots"] += 1
            consecutive_air += 1
            event = {
                "turn": turn_idx,
                "shooter": shooter,
                "action": "AIR",
                "raw": raw,
                "alive_after": [m for m in order if m in alive],
            }
            history_events.append(event)
            logger.log(f" Ход {turn_idx}: {shooter} -> AIR")

            if consecutive_air >= len(alive):
                logger.log(" Мирный исход: все оставшиеся игроки подряд выстрелили в воздух.")
                return {
                    "participants": order,
                    "winner": None,
                    "reason": "PEACE",
                    "turns": turn_idx,
                    "history": history_events,
                }
            continue

        consecutive_air = 0
        metrics["player"][shooter]["shots"] += 1
        if target:
            metrics["target_counts"][(shooter, target)] += 1
            if len(alive_list) == 3:
                metrics["targeted_3alive"][(shooter, target)] += 1
            metrics["player"][target]["times_targeted"] += 1

        hit = bool(target and random.random() < ACCURACY[shooter])
        if hit:
            alive.remove(target)
            metrics["player"][shooter]["hits"] += 1
            metrics["player"][shooter]["eliminations"] += 1
            logger.log(f" Ход {turn_idx}: {shooter} -> {target} (HIT)")
        else:
            logger.log(f" Ход {turn_idx}: {shooter} -> {target} (MISS)")

        event = {
            "turn": turn_idx,
            "shooter": shooter,
            "action": "SHOOT",
            "target": target,
            "hit": hit,
            "raw": raw,
            "alive_after": [m for m in order if m in alive],
        }
        history_events.append(event)

    if len(alive) == 1:
        winner = next(iter(alive))
        metrics["player"][winner]["wins"] += 1
        logger.log(f" Победитель: {winner}")
        return {
            "participants": order,
            "winner": winner,
            "reason": "SOLE_SURVIVOR",
            "turns": turn_idx,
            "history": history_events,
        }

    logger.log(" Игра остановлена по лимиту ходов.")
    return {
        "participants": order,
        "winner": None,
        "reason": "TURN_LIMIT",
        "turns": turn_idx,
        "history": history_events,
    }


def init_metrics() -> dict:
    return {
        "player": {
            m: {
                "turns": 0,
                "air_shots": 0,
                "shots": 0,
                "hits": 0,
                "eliminations": 0,
                "times_targeted": 0,
                "wins": 0,
            }
            for m in MODELS
        },
        "target_counts": {(a, b): 0 for a in MODELS for b in MODELS if a != b},
        "opportunities_3alive": {(a, b): 0 for a in MODELS for b in MODELS if a != b},
        "targeted_3alive": {(a, b): 0 for a in MODELS for b in MODELS if a != b},
    }


def summarize(metrics: dict, total_games: int, peace_games: int, limit_games: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    player_rows = []
    for m in MODELS:
        p = metrics["player"][m]
        turns = p["turns"]
        shots = p["shots"]
        player_rows.append(
            {
                "model": m,
                "accuracy": ACCURACY[m],
                "wins": p["wins"],
                "win_rate": p["wins"] / total_games if total_games else 0.0,
                "turns": turns,
                "air_shots": p["air_shots"],
                "air_rate": p["air_shots"] / turns if turns else 0.0,
                "shots": shots,
                "hit_rate_given_shot": p["hits"] / shots if shots else 0.0,
                "times_targeted": p["times_targeted"],
                "eliminations": p["eliminations"],
            }
        )

    pair_rows = []
    for shooter in MODELS:
        for target in MODELS:
            if shooter == target:
                continue
            opp = metrics["opportunities_3alive"][(shooter, target)]
            tgt = metrics["targeted_3alive"][(shooter, target)]
            pair_rows.append(
                {
                    "shooter": shooter,
                    "target": target,
                    "target_count_total": metrics["target_counts"][(shooter, target)],
                    "opportunities_3alive": opp,
                    "targeted_3alive": tgt,
                    "non_aggression_index_3alive": 1.0 - (tgt / opp) if opp else None,
                }
            )

    player_df = pd.DataFrame(player_rows).sort_values(by="win_rate", ascending=False)
    pair_df = pd.DataFrame(pair_rows).sort_values(by=["shooter", "target"])

    return player_df, pair_df


def run_tournament():
    logger = RunLogger()
    run_started_at = datetime.now()
    run_id = run_started_at.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"run_{run_id}"
    protocol_path = run_dir / "protocol.txt"
    summary_json_path = run_dir / "summary.json"
    player_csv_path = run_dir / "player_summary.csv"
    pair_csv_path = run_dir / "pair_behavior.csv"

    random.seed(RANDOM_SEED)

    logger.log(f"Запуск турнира: {run_started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.log(f"OpenAI-compatible base URL: {OPENAI_BASE_URL}")
    logger.log(f"Random seed: {RANDOM_SEED}")
    logger.log(f"Модели: {', '.join(MODELS)}")
    logger.log("Точности: " + ", ".join(f"{m}={ACCURACY[m]:.2f}" for m in MODELS))
    logger.log(f"Игр на каждую тройку: {GAMES_PER_TRIO}")
    logger.log(f"Лимит ходов на игру: {MAX_TURNS_PER_GAME}")

    metrics = init_metrics()
    trios = list(combinations(MODELS, 3))
    game_results = []
    peace_games = 0
    limit_games = 0

    game_id = 0
    for trio in trios:
        logger.log("\n" + "=" * 70)
        logger.log(f"Тройка: {trio}")
        logger.log("=" * 70)
        for _ in range(GAMES_PER_TRIO):
            game_id += 1
            result = play_truel(trio=trio, game_id=game_id, logger=logger, metrics=metrics)
            game_results.append(result)
            if result["reason"] == "PEACE":
                peace_games += 1
            if result["reason"] == "TURN_LIMIT":
                limit_games += 1

    total_games = len(game_results)
    player_df, pair_df = summarize(metrics, total_games=total_games, peace_games=peace_games, limit_games=limit_games)

    logger.log("\n" + "=" * 70)
    logger.log("ИТОГИ ЭКСПЕРИМЕНТА")
    logger.log("=" * 70)
    logger.log(f"Всего игр: {total_games}")
    logger.log(f"Мирных исходов: {peace_games} ({(peace_games / total_games) if total_games else 0.0:.2%})")
    logger.log(f"Остановок по лимиту: {limit_games} ({(limit_games / total_games) if total_games else 0.0:.2%})")
    logger.log("\nСводка по игрокам:")
    logger.log(player_df.to_string(index=False))
    logger.log("\nПоведенческие метрики по парам (фрагмент):")
    logger.log(pair_df.head(12).to_string(index=False))

    run_dir.mkdir(parents=True, exist_ok=True)
    player_df.to_csv(player_csv_path, index=False)
    pair_df.to_csv(pair_csv_path, index=False)

    summary_payload = {
        "run_id": run_id,
        "started_at": run_started_at.isoformat(),
        "openai_base_url": OPENAI_BASE_URL,
        "models": MODELS,
        "accuracy": ACCURACY,
        "games_per_trio": GAMES_PER_TRIO,
        "max_turns_per_game": MAX_TURNS_PER_GAME,
        "total_games": total_games,
        "peace_games": peace_games,
        "turn_limit_games": limit_games,
        "player_summary": player_df.to_dict(orient="records"),
        "pair_behavior": pair_df.to_dict(orient="records"),
        "game_results": [
            {
                "participants": r["participants"],
                "winner": r["winner"],
                "reason": r["reason"],
                "turns": r["turns"],
            }
            for r in game_results
        ],
    }
    summary_json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.log(f"\nПротокол сохранен: {protocol_path}")
    logger.log(f"CSV по игрокам: {player_csv_path}")
    logger.log(f"CSV по парам: {pair_csv_path}")
    logger.log(f"JSON сводка: {summary_json_path}")
    logger.save(protocol_path)

if __name__ == "__main__":
    run_tournament()