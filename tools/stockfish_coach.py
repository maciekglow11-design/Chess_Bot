#!/usr/bin/env python3
"""Train Chess_Bot against Stockfish in a self-improvement loop.

The script plays repeated games until interrupted (or until a fixed number of
games is reached). After each game it asks Stockfish for a deeper review of the
move choices Chess_Bot made, keeps score of the approximate loss in centipawns,
and only persists the best PGNs to a dedicated folder.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
OUR_ENGINE = [sys.executable, str(ROOT / "engine.py")]


def score_cp(score: chess.engine.PovScore, color: chess.Color) -> int:
    """Convert a score to centipawns from the perspective of the requested color."""
    return score.pov(color).score(mate_score=100_000) or 0


def our_color_for_game(choice: str, game_number: int) -> chess.Color:
    if choice == "white":
        return chess.WHITE
    if choice == "black":
        return chess.BLACK
    return chess.WHITE if game_number % 2 == 1 else chess.BLACK


def review_our_moves(stockfish: chess.engine.SimpleEngine,
                    game: chess.pgn.Game,
                    our_color: chess.Color,
                    depth: int) -> list[tuple[int, str, int, str]]:
    """Return (ply, played move, approx loss cp, best move) for Chess_Bot moves."""
    board = game.board()
    mistakes: list[tuple[int, str, int, str]] = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        if board.turn == our_color:
            before = stockfish.analyse(board, chess.engine.Limit(depth=depth))
            best_move = before.get("pv", [None])[0]
            before_score = score_cp(before["score"], our_color)
            board.push(move)
            after = stockfish.analyse(board, chess.engine.Limit(depth=depth))
            after_score = score_cp(after["score"], our_color)
            loss = max(0, before_score - after_score)
            mistakes.append((ply, move.uci(), loss, best_move.uci() if best_move else "?"))
        else:
            board.push(move)
    return mistakes


def play_game(our_engine: chess.engine.SimpleEngine,
              stockfish: chess.engine.SimpleEngine,
              our_color: chess.Color,
              limit: chess.engine.Limit,
              game_number: int,
              max_plies: int) -> chess.pgn.Game:
    board = chess.Board()
    game = chess.pgn.Game()
    game.headers["Event"] = "Chess_Bot vs Stockfish training"
    game.headers["Site"] = "Local coach"
    game.headers["Round"] = str(game_number)
    game.headers["White"] = "Chess_Bot" if our_color == chess.WHITE else "Stockfish"
    game.headers["Black"] = "Stockfish" if our_color == chess.WHITE else "Chess_Bot"
    game.headers["TimeControl"] = str(limit.time) if limit.time is not None else f"depth {limit.depth}"
    node = game

    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        is_ours = board.turn == our_color
        player = our_engine if is_ours else stockfish
        result = player.play(board, limit)
        move = result.move
        if move is None or move not in board.legal_moves:
            raise RuntimeError(f"Engine returned an illegal or missing move: {move}")
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


def persist_best_games(best_games: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("*.pgn"):
        path.unlink()

    for index, entry in enumerate(sorted(best_games, key=lambda item: item["total_loss"]), start=1):
        path = output_dir / f"best_{index:02d}_{entry['total_loss']}cp.pgn"
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        path.write_text(entry["game"].accept(exporter) + "\n", encoding="utf-8")


def keep_best_games(best_games: list[dict[str, Any]], game: chess.pgn.Game,
                   total_loss: int, keep_best: int) -> list[dict[str, Any]]:
    entry = {"game": game, "total_loss": total_loss}
    if keep_best <= 0:
        return best_games
    best_games.append(entry)
    best_games = sorted(best_games, key=lambda item: item["total_loss"])
    return best_games[:keep_best]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stockfish", required=True, help="Path to a Stockfish executable")
    parser.add_argument("--games", type=int, default=0, help="Play this many games; 0 means infinite until Ctrl-C")
    parser.add_argument("--seconds", type=float, default=1.5, help="Time per move in seconds")
    parser.add_argument("--analysis-depth", type=int, default=12, help="Stockfish analysis depth for reviewing our mistakes")
    parser.add_argument("--our-color", choices=("white", "black", "alternate"), default="alternate")
    parser.add_argument("--max-plies", type=int, default=300, help="Safety cap for a single game")
    parser.add_argument("--keep-best", type=int, default=10, help="How many best games to keep as PGN files")
    parser.add_argument("--output-dir", type=Path, default=Path("stockfish_coach_games"), help="Directory for the best saved PGNs")
    args = parser.parse_args()
    if args.games < 0:
        parser.error("--games must be non-negative")
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if args.analysis_depth < 1:
        parser.error("--analysis-depth must be positive")
    if args.keep_best < 1:
        parser.error("--keep-best must be positive")
    return args


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    stop_requested = False

    def handle_signal(signum: int, frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True
        print(f"\nStopping after current game (signal {signum}).", flush=True)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    best_games: list[dict[str, Any]] = []
    game_number = 1

    while True:
        if args.games and game_number > args.games:
            break
        if stop_requested:
            break

        print(f"\n=== Game {game_number} ===")
        our_color = our_color_for_game(args.our_color, game_number)

        limit = chess.engine.Limit(time=args.seconds)
        with chess.engine.SimpleEngine.popen_uci(OUR_ENGINE) as our_engine, \
             chess.engine.SimpleEngine.popen_uci(str(args.stockfish)) as stockfish:
            print(f"Chess_Bot color: {'White' if our_color == chess.WHITE else 'Black'}")
            game = play_game(our_engine, stockfish, our_color, limit, game_number, args.max_plies)
            mistakes = review_our_moves(stockfish, game, our_color, args.analysis_depth)
            total_loss = sum(loss for _, _, loss, _ in mistakes)
            print(f"Result: {game.headers['Result']} | total approximate loss {total_loss} cp | {len(mistakes)} reviewed moves")
            if mistakes:
                worst = max(mistakes, key=lambda item: item[2])
                print(f"Worst move: ply {worst[0]}, {worst[1]}, loss {worst[2]} cp")

            best_games = keep_best_games(best_games, game, total_loss, args.keep_best)
            persist_best_games(best_games, output_dir)
            print(f"Kept {len(best_games)} best PGNs in {output_dir.resolve()}")

        game_number += 1
        time.sleep(0.2)

    print(f"Finished training loop. Best PGNs are in: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
