#!/usr/bin/env python3
"""Play Chess_Bot against Stockfish repeatedly and review games afterward.

Stockfish is only the opponent and post-game analyst. Its recommendations are
saved as comments/diagnostics; they are never fed into Chess_Bot during a game
and this script never changes engine.py automatically.

Examples:
  python tools/stockfish_coach.py --stockfish /path/to/stockfish --loop
  python tools/stockfish_coach.py --stockfish /path/to/stockfish --games 10 --seconds 1
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
OUR_ENGINE = [sys.executable, str(ROOT / "engine.py")]
CSV_FIELDS = ("game", "ply", "color", "fen", "played", "best", "loss_cp", "before_cp", "after_cp")


def score_cp(score: chess.engine.PovScore, color: chess.Color) -> int:
    value = score.pov(color).score(mate_score=100_000)
    return 0 if value is None else value


def our_color_for_game(choice: str, game_number: int) -> chess.Color:
    if choice == "white":
        return chess.WHITE
    if choice == "black":
        return chess.BLACK
    return chess.WHITE if game_number % 2 else chess.BLACK


def bot_result_score(result: str, color: chess.Color) -> float:
    if result == "1/2-1/2":
        return 0.5
    return float(result == ("1-0" if color == chess.WHITE else "0-1"))


def should_keep_game(result: str, color: chess.Color, max_loss_cp: int,
                     loss_threshold_cp: int, minimum_result_score: float = 0.5) -> bool:
    return (bot_result_score(result, color) >= minimum_result_score
            and max_loss_cp <= loss_threshold_cp)


def _append_csv(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def review_game(stockfish: chess.engine.SimpleEngine, game: chess.pgn.Game,
                our_color: chess.Color, game_number: int, analysis_depth: int,
                csv_path: Path, positions_path: Path) -> list[dict[str, object]]:
    board = game.board()
    node = game
    review: list[dict[str, object]] = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        if board.turn != our_color:
            board.push(move)
            node = node.variation(move)
            continue

        fen = board.fen()
        before = stockfish.analyse(board, chess.engine.Limit(depth=analysis_depth))
        best_move = before.get("pv", [None])[0]
        before_cp = score_cp(before["score"], our_color)
        san = board.san(move)
        board.push(move)
        after = stockfish.analyse(board, chess.engine.Limit(depth=analysis_depth))
        after_cp = score_cp(after["score"], our_color)
        loss_cp = max(0, before_cp - after_cp)
        best_uci = best_move.uci() if best_move is not None else "?"
        label = "blunder" if loss_cp >= 250 else "mistake" if loss_cp >= 100 else "inaccuracy" if loss_cp >= 50 else ""
        node = node.variation(move)
        node.comment = (f"Stockfish review: played {san} ({move.uci()}); best {best_uci}; "
                        f"approximate loss {loss_cp} cp" + (f" — {label}" if label else ""))
        row: dict[str, object] = {
            "game": game_number, "ply": ply,
            "color": "white" if our_color == chess.WHITE else "black",
            "fen": fen, "played": move.uci(), "best": best_uci,
            "loss_cp": loss_cp, "before_cp": before_cp, "after_cp": after_cp,
        }
        review.append(row)
        _append_csv(csv_path, row)
        _append_jsonl(positions_path, {**row, "source": "stockfish", "analysis_depth": analysis_depth})
    return review


def play_game(our_engine: chess.engine.SimpleEngine, stockfish: chess.engine.SimpleEngine,
              number: int, our_color: chess.Color, limit: chess.engine.Limit,
              max_plies: int) -> chess.pgn.Game:
    board = chess.Board()
    game = chess.pgn.Game()
    game.headers["Event"] = "Chess_Bot vs Stockfish (coach)"
    game.headers["Site"] = "Local"
    game.headers["Round"] = str(number)
    game.headers["White"] = "Chess_Bot" if our_color == chess.WHITE else "Stockfish"
    game.headers["Black"] = "Stockfish" if our_color == chess.WHITE else "Chess_Bot"
    game.headers["TimeControl"] = f"depth {limit.depth}" if limit.depth is not None else str(limit.time)
    node = game

    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        is_ours = board.turn == our_color
        player = our_engine if is_ours else stockfish
        name = "Chess_Bot" if is_ours else "Stockfish"
        result = player.play(board, limit, game=game)
        move = result.move
        if move is None or move not in board.legal_moves:
            raise RuntimeError(f"{name} returned an illegal or missing move: {move}")
        print(f"Game {number}: {name} {board.san(move)} ({move.uci()})", flush=True)
        board.push(move)
        node = node.add_variation(move)

    if board.is_game_over(claim_draw=True):
        game.headers["Result"] = board.result(claim_draw=True)
        outcome = board.outcome(claim_draw=True)
        game.headers["Termination"] = outcome.termination.name if outcome else "Game over"
    else:
        game.headers["Result"] = "1/2-1/2"
        game.headers["Termination"] = f"Move limit ({max_plies} plies)"
    return game


def append_pgn(game: chess.pgn.Game, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(game.accept(exporter) + "\n\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stockfish", required=True, help="Path to installed Stockfish executable")
    parser.add_argument("--games", type=int, default=10, help="Games to play; with --loop, games per batch")
    parser.add_argument("--loop", action="store_true", help="Continue until Ctrl+C")
    parser.add_argument("--our-color", choices=("white", "black", "alternate"), default="alternate")
    parser.add_argument("--seconds", type=float, default=1.0, help="Time per move")
    parser.add_argument("--depth", type=int, help="Fixed depth instead of --seconds")
    parser.add_argument("--analysis-depth", type=int, default=10, help="Stockfish post-game review depth")
    parser.add_argument("--hash-mb", type=int, default=32, help="Hash size for each engine if supported")
    parser.add_argument("--max-plies", type=int, default=300, help="Maximum half-moves per game")
    parser.add_argument("--loss-threshold", type=int, default=150, help="Largest allowed bot move loss for saved games")
    parser.add_argument("--min-result-score", type=float, choices=(0.0, 0.5, 1.0), default=0.5,
                        help="Minimum result score to save: loss=0, draw=0.5, win=1")
    parser.add_argument("--output-dir", type=Path, default=Path("training"), help="Output directory")
    args = parser.parse_args()
    if args.games < 1 or args.hash_mb < 1 or args.max_plies < 1:
        parser.error("--games, --hash-mb, and --max-plies must be positive")
    if args.analysis_depth < 1 or args.loss_threshold < 0:
        parser.error("--analysis-depth must be positive and --loss-threshold non-negative")
    if args.depth is not None and args.depth < 1:
        parser.error("--depth must be positive")
    if args.depth is None and args.seconds <= 0:
        parser.error("--seconds must be positive")
    return args


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    limit = chess.engine.Limit(depth=args.depth) if args.depth is not None else chess.engine.Limit(time=args.seconds)
    pgn_path = args.output_dir / "strong_games.pgn"
    csv_path = args.output_dir / "move_review.csv"
    positions_path = args.output_dir / "coach_positions.jsonl"
    total = kept = wins = draws = losses = 0

    print("Stockfish is opponent/reviewer only; its analysis never changes Chess_Bot.")
    print(f"PGN: {pgn_path}\nReview CSV: {csv_path}\nPosition data: {positions_path}")
    try:
        with chess.engine.SimpleEngine.popen_uci(OUR_ENGINE) as our_engine, \
                chess.engine.SimpleEngine.popen_uci(args.stockfish) as stockfish:
            for engine in (our_engine, stockfish):
                if "Hash" in engine.options:
                    engine.configure({"Hash": args.hash_mb})
            while args.loop or total < args.games:
                number = total + 1
                color = our_color_for_game(args.our_color, number)
                game = play_game(our_engine, stockfish, number, color, limit, args.max_plies)
                review = review_game(stockfish, game, color, number, args.analysis_depth,
                                     csv_path, positions_path)
                result = game.headers["Result"]
                points = bot_result_score(result, color)
                wins += int(points == 1.0)
                draws += int(points == 0.5)
                losses += int(points == 0.0)
                max_loss = max((int(row["loss_cp"]) for row in review), default=0)
                if should_keep_game(result, color, max_loss, args.loss_threshold, args.min_result_score):
                    append_pgn(game, pgn_path)
                    kept += 1
                    print(f"Saved game {number}: {result}; largest loss {max_loss} cp.")
                else:
                    print(f"Skipped PGN {number}: {result}; largest loss {max_loss} cp.")
                total += 1
                print(f"Totals: {total} games; {wins} wins, {draws} draws, {losses} losses; {kept} saved.\n")
    except KeyboardInterrupt:
        print("\nStopped by user; completed games and review data have been saved.")
    finally:
        print(f"Final: {total} games; {wins} wins, {draws} draws, {losses} losses; {kept} saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
